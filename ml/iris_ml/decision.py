"""Decision layer: turns model probabilities into a routing decision, safely.

Order of authority (the highest urgency wins; nothing here can lower another layer's verdict):
    1. rule layer          explicit self-harm language          (rules.py)
    2. baseline floor      what the check-in already told us   (backend safety.py `urgency_floor`)
    3. model               calibrated probabilities             (this module picks the cheapest action)
    4. out-of-scope guard  empty, very short or non-English text goes to a human instead of being guessed at

The model never "clears" a message. A decision of LOW means "ordinary support is appropriate for what was written", and
only when no other layer objects and the model is confident.

Routes follow the capstone design: High -> human reviewer, Medium -> counsellor / support channel, Low -> normal support;
anything uncertain -> human reviewer.

Two policies exist, and they must not be confused:
  * the EVALUATION policy (`DecisionPolicy()`, the default) lets a confident model reach LOW without a human. It exists to
    measure what a model could do on its own, which is how the Phase 2 report was produced; its results show that no model is
    good enough to be trusted with that;
  * the V1 policy (`V1_POLICY`, `mandatory_review=True`) is the design to ship: rules + check-in floor -> the model only RANKS
    cases (`risk_score` orders the review queue) -> a human reviews every case -> the human makes the final decision. The model
    can raise priority and can never clear a case.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import HIGH, URGENCY, URGENCY_INDEX
from .metrics import load_costs
from .rules import RuleResult, scan

ROUTES = {"high": "human_reviewer", "medium": "counsellor", "low": "normal_support"}
FLOOR_INDEX = {"none": 0, "medium": URGENCY_INDEX["medium"], "high": URGENCY_INDEX["high"]}
MIN_WORDS = 3


@dataclass(frozen=True)
class DecisionPolicy:
    """Tunable policy. Defaults are conservative; operating points are chosen on development data, never on the gold set."""
    min_confidence: float = 0.60           # below this the case goes to a human regardless of the cheapest action
    review_cost: float | None = None       # None = use configs/costs.yaml
    min_words: int = MIN_WORDS
    cost_matrix: np.ndarray | None = field(default=None, compare=False)
    mandatory_review: bool = False         # True: every case goes to a human; the model only orders the queue (see V1_POLICY)


# The design to ship. `urgency` on its results is then a PROVISIONAL priority for the reviewer, never a cleared decision.
V1_POLICY = DecisionPolicy(mandatory_review=True)


@dataclass(frozen=True)
class TriageResult:
    urgency: str                       # final: max of model decision, rules and floor
    route: str                         # human_reviewer | counsellor | normal_support
    needs_human: bool
    model_urgency: str | None          # what the model alone would say
    confidence: float | None           # calibrated top probability
    risk_score: float                  # higher = more urgent; used to order the human review queue
    reasons: tuple[str, ...]           # why this decision (audit trail)
    rule_level: str
    baseline_floor: str
    probabilities: tuple[float, ...] | None = None


def expected_costs(probs: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Expected cost of predicting each urgency, given the probability of each true urgency. Shape (n, K)."""
    return np.asarray(probs, dtype=float) @ matrix            # matrix[true, predicted]


def cheapest_action(probs: np.ndarray, matrix: np.ndarray | None = None) -> np.ndarray:
    """The urgency with the lowest expected cost. With the project cost matrix this leans toward escalation."""
    m = load_costs()[0] if matrix is None else matrix
    return expected_costs(probs, m).argmin(axis=1)


def risk_score(probs: np.ndarray) -> np.ndarray:
    """Ordering key for the review queue: expected urgency level, so a case that is 40% High outranks a sure Medium."""
    p = np.asarray(probs, dtype=float)
    return p @ np.arange(p.shape[1], dtype=float)


def decide(probs: np.ndarray | None, text: str, baseline_floor: str = "none", policy: DecisionPolicy = DecisionPolicy(),
           rule: RuleResult | None = None) -> TriageResult:
    """Decide one message. `probs` may be None when no model is available (rules and floor still apply)."""
    if baseline_floor not in FLOOR_INDEX:
        raise ValueError(f"baseline_floor must be one of {list(FLOOR_INDEX)}")
    matrix, review_cost = load_costs()
    matrix = policy.cost_matrix if policy.cost_matrix is not None else matrix
    review_cost = review_cost if policy.review_cost is None else policy.review_cost
    rule = scan(text) if rule is None else rule
    reasons: list[str] = []

    model_idx: int | None = None
    conf: float | None = None
    score = 0.0
    if probs is not None:
        p = np.asarray(probs, dtype=float)
        p = p / p.sum()
        conf = float(p.max())
        model_idx = int(cheapest_action(p[None, :], matrix)[0])
        score = float(risk_score(p[None, :])[0])
        expected_best = float(expected_costs(p[None, :], matrix).min())
        if expected_best > review_cost:                       # a human is cheaper than any automated choice
            reasons.append(f"expected cost {expected_best:.2f} exceeds review cost {review_cost:.2f}")
            force_human = True
        else:
            force_human = False
        if conf < policy.min_confidence:
            reasons.append(f"confidence {conf:.2f} below {policy.min_confidence:.2f}")
            force_human = True
    else:
        force_human = True
        reasons.append("no model available")

    short = len(text.split()) < policy.min_words
    if short:
        reasons.append("message too short to judge")
        force_human = True
    if not text.isascii() and sum(c.isalpha() and c < "\u0080" for c in text) < 0.6 * max(1, sum(c.isalpha() for c in text)):
        reasons.append("text is mostly outside English (v1 supports English only)")
        force_human = True

    idx = 0 if model_idx is None else model_idx
    if rule.flagged:
        reasons.append(f"rule layer: {rule.level} ({', '.join(rule.hits)})")
        idx = max(idx, FLOOR_INDEX[rule.urgency_floor])
        score = max(score, float(FLOOR_INDEX[rule.urgency_floor]))
    if baseline_floor != "none":
        reasons.append(f"baseline floor from check-in: {baseline_floor}")
        idx = max(idx, FLOOR_INDEX[baseline_floor])
        score = max(score, float(FLOOR_INDEX[baseline_floor]))

    urgency = URGENCY[idx]
    if policy.mandatory_review:
        force_human = True
        reasons.append("mandatory human review: the model ranks, a person decides")
    needs_human = force_human or idx == HIGH or rule.level == "high"
    if needs_human and urgency != "high":
        route = ROUTES["high"]                                 # uncertain cases are read by a person
    else:
        route = ROUTES[urgency]
    if model_idx is not None and idx > model_idx:
        reasons.append("raised above the model's own decision by a safety layer")
    return TriageResult(
        urgency=urgency, route=route, needs_human=needs_human,
        model_urgency=None if model_idx is None else URGENCY[model_idx], confidence=conf, risk_score=score,
        reasons=tuple(reasons), rule_level=rule.level, baseline_floor=baseline_floor,
        probabilities=None if probs is None else tuple(float(x) for x in np.asarray(probs, float) / np.sum(probs)),
    )


NO_RULES = RuleResult(level="none", urgency_floor="none", hits=(), third_person=False, negated=False)


def decide_batch(probs: np.ndarray, texts: list[str], policy: DecisionPolicy = DecisionPolicy(),
                 floors: list[str] | None = None, use_rules: bool = True) -> list[TriageResult]:
    """`use_rules=False` is only for evaluating the model on long documents, where explicit phrases are everywhere."""
    floors = floors or ["none"] * len(texts)
    return [decide(p, t, f, policy, rule=None if use_rules else NO_RULES) for p, t, f in zip(probs, texts, floors)]


def simulate(y_true: np.ndarray, probs: np.ndarray, texts: list[str], policy: DecisionPolicy = DecisionPolicy(),
             floors: list[str] | None = None, use_rules: bool = True) -> dict:
    """Run the whole policy over labelled data and report what a safety lead needs to see."""
    y_true = np.asarray(y_true, dtype=int)
    results = decide_batch(probs, texts, policy, floors, use_rules)
    final = np.array([URGENCY_INDEX[r.urgency] for r in results])
    human = np.array([r.needs_human for r in results])
    high = y_true == HIGH
    matrix, review_cost = load_costs()
    cost = np.where(human, review_cost, matrix[y_true, final])
    return {
        "n": int(len(y_true)),
        "human_review_rate": float(human.mean()),
        "high_caught": int((human | (final == HIGH))[high].sum()), "high_total": int(high.sum()),
        "high_recall": float((human | (final == HIGH))[high].mean()) if high.any() else float("nan"),
        "high_auto_missed": int((~human & (final < HIGH))[high].sum()),     # High cases nobody would have read
        "mean_cost": float(cost.mean()),
    }
