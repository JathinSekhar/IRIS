"""Loader for the Reddit C-SSRS Suicide Dataset (Gaur et al., 2019).

Source   https://zenodo.org/records/2667859   (DOI 10.5281/zenodo.2667859)
Licence  Creative Commons Attribution 4.0 (CC-BY-4.0). Attribution is required: see the citation in DATA_REGISTRY.md.
Content  500 Reddit users, ONE row per user. `Post` is the user's whole history joined into one long document.
         `Label` is the severity a team of four psychiatrists assigned on the C-SSRS scale:
         Supportive < Indicator < Ideation < Behavior < Attempt.

Honest limits (repeated in the model card): documents not chat messages; only suicide-risk content, nothing on everyday
stress or logistics; 500 people; labels are per user, not per message.

Privacy: user ids are replaced by a one-way hash on load, links and u/mentions are masked, and the text never leaves
`data/raw` or memory except in git-ignored files.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd

from .. import ROOT, load_yaml
from ..splits import stratified_group_split

RAW_PATH = ROOT / "data" / "raw" / "reddit_cssrs" / "500_Reddit_users_posts_labels.csv"
MANIFEST_PATH = ROOT / "data" / "splits" / "reddit_cssrs_v1.csv"
SPLIT_SEED = 2026
MAX_DOC_CHARS = 50_000
SOURCE = "reddit_cssrs"

_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MENTION = re.compile(r"(?<!\w)/?u/[A-Za-z0-9_-]{2,}", re.IGNORECASE)
_MAPS = load_yaml("label_maps.yaml")["reddit_cssrs"]
NATIVE_ORDER: list[str] = _MAPS["native_order"]
VARIANTS: dict[str, dict[str, str]] = _MAPS["urgency"]
PRIMARY_VARIANT: str = _MAPS["primary_variant"]


def clean_text(text: str) -> str:
    t = _URL.sub("<url>", str(text))
    t = _MENTION.sub("<user>", t)
    return re.sub(r"\s+", " ", t).strip()


def load_raw(path: Path | str = RAW_PATH) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Download instructions are in ml/docs/DATA_REGISTRY.md")
    raw = pd.read_csv(path)
    if list(raw.columns) != ["User", "Post", "Label"]:
        raise ValueError(f"unexpected columns {list(raw.columns)}; expected ['User', 'Post', 'Label']")
    if raw[["User", "Post", "Label"]].isna().any().any():
        raise ValueError("dataset contains missing values")
    unknown = sorted(set(raw["Label"]) - set(NATIVE_ORDER))
    if unknown:
        raise ValueError(f"unknown labels {unknown}")
    if raw["User"].duplicated().any():
        raise ValueError("expected one row per user")
    return raw


def user_hash(user: str) -> str:
    return "rc-" + hashlib.sha256(f"iris:{user}".encode()).hexdigest()[:12]


def to_frame(raw: pd.DataFrame, variant: str = PRIMARY_VARIANT, seed: int = SPLIT_SEED) -> pd.DataFrame:
    """Convert to the IRIS schema (document level). The split is stratified by native label and does NOT depend on the
    urgency variant, so the held-out test users are identical under both mappings."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; choose from {list(VARIANTS)}")
    mapping = VARIANTS[variant]
    df = pd.DataFrame({
        "id": raw["User"].map(user_hash),
        "text": raw["Post"].map(clean_text),
        "native_label": raw["Label"].values,
    })
    df["group_id"] = df["id"]
    df["urgency"] = df["native_label"].map(mapping)
    df["intent"] = df["urgency"].map(lambda u: "emotional_support" if u == "low" else "crisis")
    df["source"] = SOURCE
    df["is_synthetic"] = False
    df["kind"] = "document"
    df["split"] = stratified_group_split(df["group_id"], df["native_label"], seed=seed)
    return df


def split_manifest(df: pd.DataFrame) -> pd.DataFrame:
    return df[["group_id", "native_label", "split"]].sort_values("group_id").reset_index(drop=True)


def manifest_sha256(manifest: pd.DataFrame) -> str:
    return hashlib.sha256(manifest.to_csv(index=False).encode()).hexdigest()


def verify_manifest(df: pd.DataFrame, path: Path | None = None) -> None:
    """The committed manifest is the record of which users are held out. Fail loudly if it no longer matches."""
    path = MANIFEST_PATH if path is None else Path(path)  # resolved at call time so tests can redirect it
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: write it once with write_manifest()")
    saved = pd.read_csv(path)
    now = split_manifest(df)
    if not saved.equals(now):
        raise RuntimeError("the train/val/test split no longer matches the committed manifest (reddit_cssrs_v1.csv)")


def write_manifest(df: pd.DataFrame, path: Path | None = None) -> str:
    path = MANIFEST_PATH if path is None else Path(path)
    m = split_manifest(df)
    m.to_csv(path, index=False)
    return manifest_sha256(m)
