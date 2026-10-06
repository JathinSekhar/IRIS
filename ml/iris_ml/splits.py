"""Deterministic, leakage-safe splitting.

Each group is assigned to a split by hashing (seed, group_id). Consequences that matter for evaluation:
  * every row of a group lands in the same split (no user or conversation leaks between train and test);
  * a group's split never changes when more data is added later, so published numbers stay comparable.
"""
from __future__ import annotations

import hashlib

import pandas as pd


def assign_split(group_id: str, seed: int = 0, ratios: tuple[float, float, float] = (0.7, 0.15, 0.15)) -> str:
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("ratios must sum to 1")
    digest = hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest()
    u = int(digest[:12], 16) / 16**12  # uniform in [0, 1)
    if u < ratios[0]:
        return "train"
    return "val" if u < ratios[0] + ratios[1] else "test"


def add_split(df: pd.DataFrame, group_col: str = "group_id", seed: int = 0,
              ratios: tuple[float, float, float] = (0.7, 0.15, 0.15)) -> pd.DataFrame:
    out = df.copy()
    out["split"] = out[group_col].astype(str).map(lambda g: assign_split(g, seed, ratios))
    # synthetic data is training-only, regardless of the hash
    if "is_synthetic" in out.columns:
        out.loc[out["is_synthetic"].astype(bool), "split"] = "train"
    return out


def stratified_group_split(groups: pd.Series, strata: pd.Series, seed: int = 0,
                           ratios: tuple[float, float, float] = (0.7, 0.15, 0.15)) -> pd.Series:
    """Deterministic split that keeps class proportions the same in train, val and test (for a FIXED dataset).

    Within each stratum, groups are ordered by hash(seed, group) and cut at the ratios. Needed for small datasets,
    where a plain hash split can leave a rare class almost absent from the test set. Unlike `assign_split`, a group's
    split can change if the dataset changes, so freeze the result as a manifest file.
    """
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("ratios must sum to 1")
    if groups.duplicated().any():
        raise ValueError("stratified_group_split expects one row per group")
    out = pd.Series(index=groups.index, dtype=object)
    for _, idx in strata.groupby(strata).groups.items():
        order = sorted(idx, key=lambda i: hashlib.sha256(f"{seed}:{groups[i]}".encode()).hexdigest())
        n = len(order)
        n_val = int(round(n * ratios[1]))
        n_test = int(round(n * ratios[2]))
        if n >= 3:
            n_val, n_test = max(n_val, 1), max(n_test, 1)
        n_train = n - n_val - n_test
        for k, i in enumerate(order):
            out[i] = "train" if k < n_train else ("val" if k < n_train + n_val else "test")
    return out
