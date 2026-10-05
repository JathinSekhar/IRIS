"""Safety assessment: the part of IRIS that decides whether a person may be at risk of self-harm.

This is deliberately separate from the symptom scales in `scoring.py`. Severity scores describe how someone has
been feeling; the safety assessment decides how *urgently* a human must act, which is the core of IRIS routing.

Inputs
  s0      PHQ-9 item 9 (frequency of thoughts of being better off dead or self-harm). Always asked.
  c1..c7  C-SSRS screener items, asked only when s0 > 0 (see questionnaire.py for the branching).

Triage (follows the C-SSRS screener's published triage logic)
  tier 3 high      intent (c4) or plan (c5), or suicidal behaviour within the past 3 months (c6 and c7)
  tier 2 moderate  method without intent (c3), or suicidal behaviour older than 3 months (c6 without c7)
  tier 1 low       wish to be dead (c1), thoughts without method (c2), or s0 > 0 with no other item endorsed
  tier 0 none      s0 == 0 or unanswered, nothing else endorsed

Mapping to IRIS urgency (`urgency_floor`)
  tier 3, 2  ->  "high"    route to a human reviewer immediately
  tier 1     ->  "medium"  route to counsellor / support channel, crisis resources shown
  tier 0     ->  "none"    no override

Rules
  * `urgency_floor` is a floor: downstream models may raise urgency above it, never lower it.
  * A skipped or unanswered safety item is "none", but the reviewer sees that item 9 was not answered
    (the PHQ-9 total is flagged incomplete), so silence is never mistaken for safety.
  * Any endorsement of self-harm shows crisis resources to the user straight away (`flag`).
"""
from typing import Literal, TypedDict

from .questionnaire import Answer

TIER_LABELS = ["none", "low", "moderate", "high"]
UrgencyFloor = Literal["none", "medium", "high"]


class Safety(TypedDict):
    flag: bool                    # any self-harm thought endorsed -> show crisis resources now
    tier: int                     # 0 none, 1 low, 2 moderate, 3 high
    tier_label: str
    escalate: bool                # tier >= 2 -> human review immediately
    urgency_floor: UrgencyFloor   # minimum IRIS urgency implied by the safety answers


def assess(answers: dict[str, Answer]) -> Safety:
    def yes(k: str) -> bool:
        return answers.get(k) == 1

    s0 = answers.get("s0")
    s0_positive = isinstance(s0, int) and s0 > 0

    if yes("c4") or yes("c5") or (yes("c6") and yes("c7")):
        tier = 3
    elif yes("c3") or yes("c6"):
        tier = 2
    elif yes("c1") or yes("c2") or s0_positive:
        tier = 1
    else:
        tier = 0

    floor: UrgencyFloor = "high" if tier >= 2 else "medium" if tier == 1 else "none"
    return Safety(
        flag=s0_positive or tier > 0,
        tier=tier,
        tier_label=TIER_LABELS[tier],
        escalate=tier >= 2,
        urgency_floor=floor,
    )
