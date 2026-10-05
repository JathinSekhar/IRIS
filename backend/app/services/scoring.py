"""Symptom scoring (PHQ-9, GAD-7) and the overall baseline risk. Pure functions, no I/O, fully unit-tested.

The self-harm / safety assessment lives in `safety.py` and feeds the baseline through its `urgency_floor`.

Design rules (see docs/ARCHITECTURE.md):
  * Scores are screening aids, never diagnoses, and are never shown to the end user.
  * Skipped items are not silently treated as complete: totals carry an `complete` flag.
  * Missing data yields 'unknown' risk, never 'low'.
"""
from typing import Literal, TypedDict

from .questionnaire import Answer
from .safety import Safety, assess

PHQ9_ITEMS = ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "s0"]
GAD7_ITEMS = ["g1", "g2", "g3", "g4", "g5", "g6", "g7"]

Risk = Literal["unknown", "low", "medium", "high"]


class Scale(TypedDict):
    score: int
    max: int
    band: str
    answered: int
    complete: bool


class Result(TypedDict):
    phq9: Scale
    gad7: Scale
    safety: Safety
    functioning: int | None
    baseline_risk: Risk


def phq9_band(score: int) -> str:
    if score >= 20:
        return "severe"
    if score >= 15:
        return "moderately_severe"
    if score >= 10:
        return "moderate"
    if score >= 5:
        return "mild"
    return "minimal"


def gad7_band(score: int) -> str:
    if score >= 15:
        return "severe"
    if score >= 10:
        return "moderate"
    if score >= 5:
        return "mild"
    return "minimal"


def _scale(items: list[str], answers: dict[str, Answer], maximum: int, band) -> Scale:
    vals = [answers[i] for i in items if isinstance(answers.get(i), int)]
    total = sum(vals)  # type: ignore[arg-type]
    return Scale(score=total, max=maximum, band=band(total), answered=len(vals), complete=len(vals) == len(items))


def score(answers: dict[str, Answer]) -> Result:
    phq = _scale(PHQ9_ITEMS, answers, 27, phq9_band)
    gad = _scale(GAD7_ITEMS, answers, 21, gad7_band)
    safety = assess(answers)
    f1 = answers.get("f1")
    functioning = f1 if isinstance(f1, int) else None

    if not answers:
        risk: Risk = "unknown"
    elif safety["urgency_floor"] == "high" or phq["score"] >= 20:
        risk = "high"
    elif safety["urgency_floor"] == "medium" or phq["score"] >= 10 or gad["score"] >= 10 or (functioning or 0) >= 2:
        risk = "medium"
    else:
        risk = "low"
    return Result(phq9=phq, gad7=gad, safety=safety, functioning=functioning, baseline_risk=risk)
