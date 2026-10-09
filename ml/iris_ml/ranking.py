"""Ranking metrics and paired model comparison (Phase 2).

Why ranking: the product can read only so many messages. What matters is how many High cases a reviewer finds when
reading the top share of the queue, ordered by risk score. These functions answer that, and answer "is model B really
better than model A, or is that noise?" on the same cases.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from . import HIGH
from .metrics import wilson_interval


def _ints(x: Sequence[int]) -> np.ndarray:
    return np.asarray(x, dtype=int)


def recall_at_review_rate(y_true: Sequence[int], score: Sequence[float], rates: Sequence[float]) -> pd.DataFrame:
    """If reviewers read the top `rate` of cases ranked by `score`, what share of High cases do they see?

    Reading at random finds about `rate` of them, so any value above that is the model's contribution.
    """
    y_true = _ints(y_true)
    score = np.asarray(score, dtype=float)
    order = np.lexsort((np.arange(len(score)), -score))          # highest score first, ties by position (deterministic)
    high = y_true == HIGH
    n_high = int(high.sum())
    rows = []
    for r in rates:
        k = int(math.ceil(r * len(y_true)))
        seen = int(high[order[:k]].sum())
        lo, hi = wilson_interval(seen, n_high)
        rows.append({"review_rate": float(r), "cases_read": k, "high_seen": seen, "high_total": n_high,
                     "recall": seen / n_high if n_high else float("nan"), "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows)


def auroc_high(y_true: Sequence[int], score: Sequence[float]) -> float:
    from sklearn.metrics import roc_auc_score
    high = _ints(y_true) == HIGH
    return float(roc_auc_score(high, score)) if 0 < high.sum() < len(high) else float("nan")


def pr_auc_high(y_true: Sequence[int], score: Sequence[float]) -> float:
    from sklearn.metrics import average_precision_score
    high = _ints(y_true) == HIGH
    return float(average_precision_score(high, score)) if high.any() else float("nan")


def paired_bootstrap_diff(metric: Callable[[np.ndarray, np.ndarray], float], y_true: Sequence[int],
                          a: Sequence, b: Sequence, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> dict:
    """metric(B) - metric(A) on the SAME resampled cases. If the interval contains 0, the models are not distinguishable."""
    y_true, a, b = _ints(y_true), np.asarray(a), np.asarray(b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(y_true), size=(n_boot, len(y_true)))
    diffs = np.array([metric(y_true[i], b[i]) - metric(y_true[i], a[i]) for i in idx], dtype=float)
    lo, hi = np.nanpercentile(diffs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    point = metric(y_true, b) - metric(y_true, a)
    return {"diff": float(point), "ci_low": float(lo), "ci_high": float(hi), "distinguishable": bool(lo > 0 or hi < 0)}


def mcnemar_exact(correct_a: Sequence[bool], correct_b: Sequence[bool]) -> dict:
    """Exact McNemar test on paired correctness (e.g. 'caught this High case'). Only disagreements carry information."""
    from scipy.stats import binomtest
    a, b = np.asarray(correct_a, bool), np.asarray(correct_b, bool)
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    n = only_a + only_b
    p = 1.0 if n == 0 else float(binomtest(only_b, n, 0.5).pvalue)
    return {"only_a_correct": only_a, "only_b_correct": only_b, "p_value": p}
