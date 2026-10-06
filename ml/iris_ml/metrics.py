"""Evaluation harness. Written first, before any model, so every model is judged by the same code.

Headline metric: recall on High urgency, always reported with a confidence interval. With a few hundred test
items the interval is wide; reporting it prevents over-claiming. Cost, calibration and the human-review tradeoff
follow from IRIS's safety principle: missing an urgent case is much worse than escalating a non-urgent one.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix, precision_recall_fscore_support

from . import HIGH, URGENCY, load_yaml


def _ints(x: Sequence[int]) -> np.ndarray:
    return np.asarray(x, dtype=int)


# --- proportions ------------------------------------------------------------------------------------------------

def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. Better than the normal approximation for small n or p near 1."""
    if n == 0:
        return 0.0, 1.0  # no information at all
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def recall_with_ci(y_true: Sequence[int], y_pred: Sequence[int], label: int = HIGH) -> dict:
    y_true, y_pred = _ints(y_true), _ints(y_pred)
    mask = y_true == label
    total = int(mask.sum())
    caught = int((y_pred[mask] == label).sum())
    lo, hi = wilson_interval(caught, total)
    return {"recall": caught / total if total else float("nan"), "caught": caught, "total": total,
            "ci_low": lo, "ci_high": hi}


def bootstrap_ci(metric: Callable[[np.ndarray, np.ndarray], float], y_true: Sequence[int], y_pred: Sequence[int],
                 n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    """Paired percentile bootstrap for any metric(y_true, y_pred)."""
    y_true, y_pred = _ints(y_true), _ints(y_pred)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(y_true), size=(n_boot, len(y_true)))
    vals = np.array([metric(y_true[i], y_pred[i]) for i in idx], dtype=float)
    lo, hi = np.nanpercentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


# --- classification report --------------------------------------------------------------------------------------

def urgency_report(y_true: Sequence[int], y_pred: Sequence[int]) -> dict:
    y_true, y_pred = _ints(y_true), _ints(y_pred)
    labels = list(range(len(URGENCY)))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    per_class = {URGENCY[i]: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])}
                 for i in labels}
    try:
        qwk = float(cohen_kappa_score(y_true, y_pred, weights="quadratic", labels=labels))
    except ValueError:
        qwk = float("nan")
    return {
        "high_recall": recall_with_ci(y_true, y_pred),
        "per_class": per_class,
        "macro_f1": float(np.mean(f)),
        "quadratic_weighted_kappa": qwk,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),  # rows true, columns predicted
        "n": int(len(y_true)),
    }


# --- calibration ------------------------------------------------------------------------------------------------

def reliability_table(probs: np.ndarray, y_true: Sequence[int], n_bins: int = 10) -> pd.DataFrame:
    """Per confidence bin: how many predictions, their mean confidence and their actual accuracy."""
    probs = np.asarray(probs, dtype=float)
    y_true = _ints(y_true)
    conf, pred = probs.max(axis=1), probs.argmax(axis=1)
    correct = (pred == y_true).astype(float)
    bins = np.minimum((conf * n_bins).astype(int), n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = bins == b
        rows.append({"bin": b, "low": b / n_bins, "high": (b + 1) / n_bins, "count": int(m.sum()),
                     "mean_confidence": float(conf[m].mean()) if m.any() else float("nan"),
                     "accuracy": float(correct[m].mean()) if m.any() else float("nan")})
    return pd.DataFrame(rows)


def ece(probs: np.ndarray, y_true: Sequence[int], n_bins: int = 10) -> float:
    """Expected calibration error (top-label). 0 means the confidence can be taken at face value."""
    t = reliability_table(probs, y_true, n_bins)
    t = t[t["count"] > 0]
    n = t["count"].sum()
    return float((t["count"] / n * (t["accuracy"] - t["mean_confidence"]).abs()).sum())


# --- cost and the human-review tradeoff -------------------------------------------------------------------------

def load_costs() -> tuple[np.ndarray, float]:
    cfg = load_yaml("costs.yaml")
    matrix = np.array([cfg["matrix"][name] for name in URGENCY], dtype=float)
    if matrix.shape != (len(URGENCY), len(URGENCY)):
        raise ValueError("cost matrix must be urgency x urgency")
    return matrix, float(cfg["review_cost"])


def expected_cost(y_true: Sequence[int], y_pred: Sequence[int], matrix: np.ndarray | None = None) -> float:
    """Mean cost per message of the automated decisions alone (no human review)."""
    m = load_costs()[0] if matrix is None else matrix
    return float(m[_ints(y_true), _ints(y_pred)].mean())


def review_curve(y_true: Sequence[int], probs: np.ndarray, thresholds: Sequence[float],
                 matrix: np.ndarray | None = None, review_cost: float | None = None) -> pd.DataFrame:
    """Sweep a confidence threshold: below it, a case goes to a human reviewer who resolves it correctly.

    Shows the central tradeoff of IRIS: more human review catches more urgent cases but costs reviewer time.
    A High case counts as caught if the model predicted High OR a human saw it.
    """
    m, rc = load_costs()
    m = m if matrix is None else matrix
    rc = rc if review_cost is None else review_cost
    y_true = _ints(y_true)
    probs = np.asarray(probs, dtype=float)
    conf, pred = probs.max(axis=1), probs.argmax(axis=1)
    high = y_true == HIGH
    rows = []
    for tau in thresholds:
        reviewed = conf < tau
        cost = np.where(reviewed, rc, m[y_true, pred])
        caught = (reviewed | (pred == HIGH))[high]
        rows.append({"threshold": float(tau), "review_rate": float(reviewed.mean()),
                     "high_recall": float(caught.mean()) if high.any() else float("nan"),
                     "mean_cost": float(cost.mean())})
    return pd.DataFrame(rows)


def cheapest_review_for_recall(curve: pd.DataFrame, target: float) -> pd.Series | None:
    """The operating point with the lowest review rate that still reaches the recall target, or None."""
    ok = curve[curve["high_recall"] >= target]
    return None if ok.empty else ok.sort_values(["review_rate", "mean_cost"]).iloc[0]


# --- slices -----------------------------------------------------------------------------------------------------

def slice_high_recall(df: pd.DataFrame, slice_col: str, y_true_col: str = "y_true", y_pred_col: str = "y_pred",
                      min_high: int = 1) -> pd.DataFrame:
    """High-urgency recall per slice (language, negation, third person, ...) with Wilson intervals and counts."""
    rows = []
    for value, g in df.groupby(slice_col):
        r = recall_with_ci(g[y_true_col], g[y_pred_col])
        if r["total"] >= min_high:
            rows.append({slice_col: value, "n_high": r["total"], "caught": r["caught"], "recall": r["recall"],
                         "ci_low": r["ci_low"], "ci_high": r["ci_high"]})
    return pd.DataFrame(rows)
