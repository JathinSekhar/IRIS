"""Inter-annotator agreement for the gold test set. Target from the plan: kappa >= 0.6."""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from sklearn.metrics import cohen_kappa_score

from . import INTENT, URGENCY, URGENCY_INDEX

KAPPA_TARGET = 0.6


def cohens_kappa(a: Sequence, b: Sequence, weights: str | None = None) -> float:
    """Cohen's kappa. Returns 1.0 when both annotators used one identical label throughout (kappa is undefined there)."""
    a, b = list(a), list(b)
    if len(a) != len(b) or not a:
        raise ValueError("annotation lists must be the same non-zero length")
    if len(set(a) | set(b)) == 1:
        return 1.0
    return float(cohen_kappa_score(a, b, weights=weights))


def compare(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Compare two annotators' labels on the same ids. Urgency is ordinal, so it uses quadratic weighting."""
    m = a.merge(b, on="id", suffixes=("_a", "_b"))
    if m.empty:
        raise ValueError("the two annotation sets share no ids")
    ua = m["urgency_a"].map(URGENCY_INDEX)
    ub = m["urgency_b"].map(URGENCY_INDEX)
    k_urg = cohens_kappa(ua, ub, weights="quadratic")
    k_int = cohens_kappa(m["intent_a"], m["intent_b"])
    return {
        "n": int(len(m)),
        "urgency_kappa_quadratic": k_urg,
        "intent_kappa": k_int,
        "urgency_exact_agreement": float((ua == ub).mean()),
        "meets_target": bool(k_urg >= KAPPA_TARGET and k_int >= KAPPA_TARGET),
    }


def to_adjudicate(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Every item where the annotators differ on urgency or intent. A counsellor settles these, High/crisis first."""
    m = a.merge(b, on="id", suffixes=("_a", "_b"))
    diff = m[(m["urgency_a"] != m["urgency_b"]) | (m["intent_a"] != m["intent_b"])].copy()
    diff["involves_high"] = (diff["urgency_a"] == "high") | (diff["urgency_b"] == "high")
    return diff.sort_values("involves_high", ascending=False).reset_index(drop=True)


__all__ = ["KAPPA_TARGET", "cohens_kappa", "compare", "to_adjudicate", "INTENT", "URGENCY"]
