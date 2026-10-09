"""The Phase 2 triage system: scorer + calibration + decision layer, plus the audits that matter for a safe rollout.

    TriageSystem.triage(text, baseline_floor)  ->  TriageResult   (rules, check-in floor, model, cost-sensitive policy)

Audits
  esconv_workload   how many ORDINARY support messages would a policy send to a human? (the cost of false alarms)
  challenge         regression and false-alarm check on the hand-written challenge set (NOT gold, see challenge.py)

The scorer is fitted on development users (plus flagged synthetic messages, if the spec says so). Its temperature comes from
cross-validated calibration on documents; on short messages calibration is unverified, which every report states.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import URGENCY, ROOT
from .calibration import adjust_prior, apply_temperature
from .challenge import challenge_frame, evaluate_challenge
from .decision import NO_RULES, DecisionPolicy, TriageResult, decide, decide_batch
from .experiments import Prepared, Spec, _full_proba, fit_split
from .rules import scan

ESCONV_PATH = ROOT / "data" / "raw" / "esconv" / "ESConv.json"


@dataclass
class TriageSystem:
    name: str
    predict_proba: object            # callable: list[str] -> (n, 3) probabilities (uncalibrated)
    temperature: float = 1.0
    policy: DecisionPolicy = DecisionPolicy()
    spec: Spec | None = None
    artifact: tuple | None = None    # what save_system persists
    prior: tuple | None = None       # (source_prior, target_prior) or None. Default None = no shift. See calibration.adjust_prior

    def probabilities(self, texts: list[str]) -> np.ndarray:
        p = apply_temperature(np.asarray(self.predict_proba(list(texts)), dtype=float), self.temperature)
        return p if self.prior is None else adjust_prior(p, np.asarray(self.prior[0]), np.asarray(self.prior[1]))

    def triage_batch(self, texts: list[str], floors: list[str] | None = None, use_rules: bool = True,
                     policy: DecisionPolicy | None = None) -> list[TriageResult]:
        """Fail safe: if the model errors or returns something unusable, every message still gets the rule layer and the
        check-in floor, and goes to a human. A broken model can never turn into 'low'."""
        try:
            probs = self.probabilities(texts)
            if probs.shape != (len(texts), len(URGENCY)) or not np.isfinite(probs).all():
                raise ValueError("model returned invalid probabilities")
        except Exception:
            return [decide(None, t, (floors or ["none"] * len(texts))[i], policy or self.policy,
                           rule=None if use_rules else NO_RULES) for i, t in enumerate(texts)]
        return decide_batch(probs, list(texts), policy or self.policy, floors, use_rules)

    def triage(self, text: str, baseline_floor: str = "none") -> TriageResult:
        return self.triage_batch([text], [baseline_floor])[0]


def ensemble_system(name: str, members: list[TriageSystem], policy: DecisionPolicy = DecisionPolicy()) -> TriageSystem:
    """Mean of the members' CALIBRATED probabilities. Each member keeps its own temperature."""
    if not members:
        raise ValueError("an ensemble needs at least one member")

    def predict(texts):
        return np.mean([m.probabilities(list(texts)) for m in members], axis=0)
    return TriageSystem(name, predict, 1.0, policy, None, ("ensemble", members))


def with_prior(system: TriageSystem, source_prior, target_high: float | None) -> TriageSystem:
    """A copy of the system whose probabilities assume a population with `target_high` share of High (None = no shift)."""
    from dataclasses import replace
    from .calibration import prior_with_high
    if target_high is None:
        return replace(system, prior=None)
    return replace(system, prior=(tuple(np.asarray(source_prior, float)), tuple(prior_with_high(np.asarray(source_prior, float), target_high))))


def fit_final(spec: Spec, prep: Prepared, embed_fn, temperature: float, policy: DecisionPolicy = DecisionPolicy(),
              seed: int = 2026) -> TriageSystem:
    """Fit the spec on ALL development users (never the held-out test users) and return a message-level system."""
    fitted = fit_split(spec, prep, np.arange(len(prep.y)), embed_fn, seed=seed)
    if fitted.predict_texts is None:
        raise ValueError(f"{spec.family} cannot score single messages")
    return TriageSystem(spec.name, fitted.predict_texts, temperature, policy, spec, fitted.artifact)


# --- audits -----------------------------------------------------------------------------------------------------------------

def esconv_messages(n: int = 6000, seed: int = 2026, path: Path = ESCONV_PATH) -> list[str]:
    """Chat-style seeker messages from ESConv (academic-research-only licence: used ONLY for this audit, never for training)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    msgs = [t["content"].strip() for c in d for t in c["dialog"] if t["speaker"] == "seeker"]
    msgs = [m for m in msgs if 3 <= len(m.split()) <= 150]
    rng = np.random.default_rng(seed)
    return [msgs[i] for i in rng.permutation(len(msgs))[:n]]


def workload(system: TriageSystem, texts: list[str], min_confidences=(0.5, 0.6, 0.7, 0.8), use_rules: bool = True) -> dict:
    """Share of ordinary support messages that each policy would send to a human, escalate, or leave as ordinary support."""
    probs = system.probabilities(texts)
    out = {"n": len(texts), "rule_flag_rate": float(np.mean([scan(t).flagged for t in texts])), "by_min_confidence": {}}
    for mc in min_confidences:
        res = decide_batch(probs, texts, DecisionPolicy(min_confidence=mc), use_rules=use_rules)
        u = np.array([r.urgency for r in res])
        out["by_min_confidence"][f"{mc:.2f}"] = {
            "needs_human": float(np.mean([r.needs_human for r in res])),
            "final_low": float(np.mean(u == "low")), "final_medium": float(np.mean(u == "medium")),
            "final_high": float(np.mean(u == "high")),
        }
    out["mean_confidence"] = float(probs.max(axis=1).mean())
    out["model_says_medium_or_high"] = float((probs.argmax(axis=1) >= 1).mean())
    return out


def challenge(system: TriageSystem | None, use_model: bool = True) -> dict:
    """Run the challenge set. `system=None` evaluates the rule layer alone (the floor every other result must beat)."""
    df = challenge_frame()
    texts = list(df["text"])
    if system is None:
        urgency, human = [], []
        for t in texts:
            lvl = scan(t).level
            urgency.append({"none": "low", "review": "medium", "high": "high"}[lvl])
            human.append(lvl == "high")
        return evaluate_challenge(texts, urgency, human)
    res = system.triage_batch(texts)
    return evaluate_challenge(texts, [r.urgency for r in res], [r.needs_human for r in res])


# --- saving and loading the deployable system -----------------------------------------------------------------------------------

def save_system(system: TriageSystem, directory: Path, extra: dict | None = None) -> Path:
    """Persist scorer + calibration + policy + spec. Third-party text is never stored, only learned parameters."""
    import joblib
    import torch
    from dataclasses import asdict
    if system.artifact is None:
        raise ValueError("this system has no persistable artefact (fine-tuned transformers are not supported yet)")
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    kind, obj = system.artifact
    if kind == "ensemble":
        for i, m in enumerate(obj):
            save_system(m, d / f"member_{i}")
        (d / "system.json").write_text(json.dumps({"kind": "ensemble", "name": system.name, "members": len(obj),
                                                   "min_confidence": system.policy.min_confidence, **(extra or {})}, indent=1),
                                       encoding="utf-8")
        return d
    if system.spec is None:
        raise ValueError("this system has no persistable artefact (fine-tuned transformers are not supported yet)")
    if kind == "sklearn":
        joblib.dump(obj, d / "model.joblib")
    elif kind == "mil":
        torch.save({"state": obj.state_dict(), "in_dim": obj.v.in_features, "hidden": obj.v.out_features,
                    "head": system.spec.head}, d / "model.pt")
    else:
        raise ValueError(kind)
    meta = {"spec": asdict(system.spec), "kind": kind, "temperature": system.temperature,
            "min_confidence": system.policy.min_confidence, **(extra or {})}
    (d / "system.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return d


def load_system(directory: Path, embed_fn=None) -> TriageSystem:
    import joblib
    import torch
    from . import embeddings, neural
    d = Path(directory)
    meta = json.loads((d / "system.json").read_text(encoding="utf-8"))
    if meta["kind"] == "ensemble":
        members = [load_system(d / f"member_{i}", embed_fn) for i in range(meta["members"])]
        return ensemble_system(meta["name"], members, DecisionPolicy(min_confidence=meta["min_confidence"]))
    spec = Spec(**meta["spec"])
    embed_fn = embed_fn or embeddings.embed
    if meta["kind"] == "sklearn":
        obj = joblib.load(d / "model.joblib")
        if spec.family in ("doc_tfidf", "chunk_tfidf"):
            cut = 20_000 if spec.family == "doc_tfidf" else None
            predict = lambda ts: _full_proba(obj.named_steps["clf"],
                                             obj.named_steps["tfidf"].transform([x[:cut] if cut else x for x in ts]))
        else:
            predict = lambda ts: _full_proba(obj, embed_fn(list(ts), spec.embedder))
    else:
        z = torch.load(d / "model.pt", map_location=neural.device(), weights_only=True)
        model = neural.AttentionMIL(z["in_dim"], hidden=z["hidden"], kind=z["head"]).to(neural.device())
        model.load_state_dict(z["state"])
        model.eval()

        def predict(ts):
            e = embed_fn(list(ts), spec.embedder)
            return neural.predict_mil(model, [e[i:i + 1] for i in range(len(e))])[0]
        obj = model
    return TriageSystem(spec.name, predict, meta["temperature"], DecisionPolicy(min_confidence=meta["min_confidence"]),
                        spec, (meta["kind"], obj))
