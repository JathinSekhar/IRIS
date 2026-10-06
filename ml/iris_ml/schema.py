"""The one dataset schema every source is converted to, and the checks that keep evaluation honest.

Columns
  required: id, text, intent, urgency, source, split, is_synthetic, group_id
  optional: subject (self | third_party | unclear), uncertain (0/1), lang, context

`group_id` is the unit that must never be split across train/val/test: a Reddit user, a conversation, or the
original message that a synthetic variant was derived from.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

from . import INTENT, SPLITS, SUBJECT, URGENCY

REQUIRED = ["id", "text", "intent", "urgency", "source", "split", "is_synthetic", "group_id"]
MAX_TEXT_CHARS = 5000


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text)).lower()).strip()


def validate(df: pd.DataFrame, max_chars: int = MAX_TEXT_CHARS) -> list[str]:
    """Return a list of human-readable problems. An empty list means the frame is safe to train and evaluate on."""
    problems: list[str] = []
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        return [f"missing required columns: {missing}"]

    if df["id"].duplicated().any():
        problems.append(f"{int(df['id'].duplicated().sum())} duplicate ids")

    empty = df["text"].isna() | (df["text"].astype(str).str.strip() == "")
    if empty.any():
        problems.append(f"{int(empty.sum())} empty texts")
    if (df["text"].astype(str).str.len() > max_chars).any():
        problems.append(f"texts longer than {max_chars} characters")

    for col, allowed in (("intent", INTENT), ("urgency", URGENCY), ("split", SPLITS)):
        bad = ~df[col].isin(allowed)
        if bad.any():
            problems.append(f"{int(bad.sum())} rows with invalid {col} (allowed: {allowed}); e.g. {df.loc[bad, col].iloc[0]!r}")
    if "subject" in df.columns:
        bad = df["subject"].notna() & ~df["subject"].isin(SUBJECT)
        if bad.any():
            problems.append(f"{int(bad.sum())} rows with invalid subject")

    synthetic = df["is_synthetic"].astype(bool)
    if (synthetic & (df["split"] != "train")).any():
        problems.append("synthetic rows outside the train split (synthetic data must never be used to evaluate)")

    # Clinical consistency rules from the labelling guide.
    if ((df["intent"] == "crisis") & (df["urgency"] == "low")).any():
        problems.append("intent=crisis with urgency=low (crisis must be at least medium)")
    if ((df["urgency"] == "high") & (df["intent"] != "crisis")).any():
        problems.append("urgency=high with intent other than crisis")

    # Leakage: the same group, or the same text, in more than one split.
    splits_per_group = df.groupby("group_id")["split"].nunique()
    leaking = splits_per_group[splits_per_group > 1]
    if len(leaking):
        problems.append(f"{len(leaking)} group_id values appear in more than one split (e.g. {leaking.index[0]!r})")
    norm = df["text"].map(_norm)
    splits_per_text = df.assign(_n=norm).groupby("_n")["split"].nunique()
    dup_text = splits_per_text[splits_per_text > 1]
    if len(dup_text):
        problems.append(f"{len(dup_text)} identical texts appear in more than one split")
    return problems


def assert_valid(df: pd.DataFrame, max_chars: int = MAX_TEXT_CHARS) -> pd.DataFrame:
    problems = validate(df, max_chars)
    if problems:
        raise ValueError("dataset failed validation:\n  - " + "\n  - ".join(problems))
    return df
