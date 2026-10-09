"""Adapter between the web app and the ML package (`ml/iris_ml`).

NO MODEL IS LOADED. The Phase 2 evaluation found no model good enough to categorise messages (they find about half the High cases at 30% review and
flag most ordinary chat as High; see ml/reports/phase2_final_summary.md). So priority here comes only from:

    the rule layer (explicit self-harm language)  +  the check-in safety floor   ->  highest urgency wins, nothing can lower it

and EVERY message is placed in the human review queue (the V1 policy: mandatory review). `MODEL_VERSION` says so on every stored prediction. When a model
is justified by a gold-set evaluation, it plugs in through `decide(probs, ...)` and may only RANK the queue; it can never clear a case.

The wording the person sees comes from `iris_ml.support` (a fixed, reviewable list). It is an AI-assisted draft pending clinical review.
"""
from __future__ import annotations

import sys

from ..config import settings

if settings.ml_path not in sys.path:
    sys.path.insert(0, settings.ml_path)

from iris_ml import support  # noqa: E402
from iris_ml.decision import V1_POLICY, TriageResult, decide  # noqa: E402

MODEL_VERSION = "none: rules + check-in floor only"
POLICY_VERSION = "v1-mandatory-review"
PENDING = support.QUEUE_STATUS          # "pending_human_review"
REVIEWED = "reviewed"
URGENCY_RANK = {"high": 0, "medium": 1, "low": 2}


def baseline_floor(checkin_scores: dict | None) -> tuple[str, bool]:
    """(floor, known). The floor comes from the self-harm (C-SSRS) answers of the latest completed check-in. No check-in means unknown, never 'safe'."""
    if not checkin_scores:
        return "none", False
    floor = (checkin_scores.get("safety") or {}).get("urgency_floor", "none")
    return (floor if floor in ("none", "medium", "high") else "none"), True


def run(text: str, floor: str) -> tuple[TriageResult, support.SupportPlan]:
    result = decide(None, text, floor, V1_POLICY)         # probs=None: no model. Rules and the floor still apply; a person reads every case.
    return result, support.plan_support(text, result)


def reply_json(plan: support.SupportPlan) -> dict:
    """Only what the person may see. No urgency label, score, topic code or reason."""
    return {
        "layout": plan.layout, "helplines": [{"name": n, "detail": d, "number": num, "tel": tel} for n, d, num, tel in plan.helplines],
        "intro": plan.intro, "listening": plan.listening,
        "self_help": [{"title": t, "how": h} for t, h in plan.self_help], "reach_out": list(plan.reach_out),
        "crisis_lead": plan.crisis_lead, "crisis_lines": list(plan.crisis_lines), "show_crisis_resources": plan.show_crisis_resources,
        "emergency_footer": plan.emergency_footer, "closing": plan.closing, "a_person_may_reach_out": plan.a_person_may_reach_out,
    }


def care_status(status: str, first_opened_at) -> str:
    """The truth about a message: 'reviewed' once a reviewer recorded a judgement, 'being_read' once one has opened it, otherwise 'waiting'."""
    if status == REVIEWED:
        return "reviewed"
    return "being_read" if first_opened_at is not None else "waiting"


def is_urgent(urgency: str, rule_level: str) -> bool:
    return urgency == "high" or rule_level == "high"


def result_from_row(urgency: str, risk_score: float, reasons: list[str], rule_level: str, floor: str) -> TriageResult:
    """Rebuild the decision from stored fields, so the library can regenerate the reviewer note after an escalation."""
    return TriageResult(urgency=urgency, route="human_reviewer", needs_human=True, model_urgency=None, confidence=None, risk_score=risk_score,
                        reasons=tuple(reasons), rule_level=rule_level, baseline_floor=floor)


def reviewer_note(urgency: str, risk_score: float, reasons: list[str], rule_level: str, floor: str) -> str:
    r = result_from_row(urgency, risk_score, reasons, rule_level, floor)
    return support.reviewer_note(r, urgent=(urgency == "high" or rule_level == "high"))
