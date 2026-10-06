"""Gold test set workflow: sample, hand out blind batches, check agreement, adjudicate, freeze.

    python -m iris_ml.gold build      # sample message-sized segments from the HELD-OUT users; write batches
    python -m iris_ml.gold check      # after labelling: validate both annotators, agreement, adjudication sheet
    python -m iris_ml.gold finalize   # after adjudication: write gold_v1.csv and freeze it (sha256)

WHO LABELS: two human annotators, independently and blind, then a counsellor adjudicates disagreements, using
docs/LABELING_GUIDE.md once a clinician has signed it off. This code never assigns a label itself, and nothing here
pre-labels an item: showing a suggested label would anchor the annotators and ruin the independence that makes the gold
set trustworthy.

WHY SEGMENTS FROM THE TEST USERS: the pool is drawn only from the 76 users held out in the frozen split, so no gold item
shares a person with training data. Annotators never see the original psychiatrist label or the rule-layer result, so
their labels are an independent check that can later be compared with the per-user clinical labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import INTENT, ROOT, SUBJECT, URGENCY
from .agreement import compare, cohens_kappa, to_adjudicate
from .rules import scan
from .schema import assert_valid
from .segment import windows

GOLD_DIR = ROOT / "data" / "gold"
SOURCE = "gold_reddit_segments"
REPEAT_SUFFIX = "~r"
LABEL_COLUMNS = ["intent", "urgency", "subject", "uncertain", "notes"]
ANNOTATOR_COLUMNS = ["id", "text", *LABEL_COLUMNS]
N_TARGET = 300


# --- sampling ---------------------------------------------------------------------------------------------------

def _hash(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()


# SAMPLING AID ONLY. These words make a segment more likely to describe an attempt, a method or imminence, so the pool
# contains enough potentially urgent items. They never decide a label: annotators label every item from scratch.
_SIGNAL = re.compile(
    r"\b(?:attempt(?:ed|s)?|overdos\w*|pills?|tablets?|hospital|er|ambulance|911|112|psych\s*ward|rope|noose|"
    r"hang(?:ed|ing)?|jump(?:ed|ing)?|bridge|gun|razor|blade|cut(?:ting)?|wrists?|plan(?:ned|ning)?|note|goodbye|"
    r"tonight|tomorrow|survive[ds]?|woke\s+up\s+in)\b", re.IGNORECASE)


def has_signal(text: str) -> bool:
    return bool(_SIGNAL.search(text))


def english_like(text: str) -> bool:
    """Cheap filter: mostly ASCII letters, real words, not a wall of links. v1 labels English only."""
    if len(text.split()) < 20:
        return False
    ascii_share = sum(c < "\u0080" for c in text) / len(text)
    alpha_share = sum(c.isalpha() or c.isspace() for c in text) / len(text)
    return ascii_share >= 0.95 and alpha_share >= 0.80 and text.count("<url>") <= 1


def build_pool(test_docs: pd.DataFrame, n_target: int = N_TARGET, per_user_cap: int = 6, seed: int = 2026) -> pd.DataFrame:
    """Round-robin stratified sample of segments. Strata = psychiatrist label x rule-layer level x risk-vocabulary flag,
    so the pool contains hard cases on both sides: explicit phrases in low-risk users, and high-risk users with no
    explicit phrase at all, and enough attempt/method/imminence vocabulary to surface potentially urgent items.
    Small strata are exhausted first, which keeps rare and difficult cases well represented."""
    if (test_docs["split"] != "test").any():
        raise ValueError("the gold pool may only be drawn from held-out test users")
    cells: dict[str, list[dict]] = defaultdict(list)
    for _, r in test_docs.iterrows():
        for seg in windows(r["text"], min_chars=120, max_chars=600, max_sentences=4):
            if not english_like(seg):
                continue
            lvl = scan(seg).level
            sig = has_signal(seg)
            stratum = f"{r['native_label']}|{lvl}|{'signal' if sig else 'plain'}"
            cells[stratum].append(
                {"id": "gold-" + hashlib.sha256(seg.encode()).hexdigest()[:10], "text": seg, "group_id": r["group_id"],
                 "native_label": r["native_label"], "rules_level": lvl, "signal": sig, "stratum": stratum})
    for rows in cells.values():
        rows.sort(key=lambda x: _hash(seed, x["id"]))
    pointers = {k: 0 for k in cells}
    per_user: dict[str, int] = defaultdict(int)
    chosen: list[dict] = []
    seen_ids: set[str] = set()
    while len(chosen) < n_target:
        progressed = False
        for key in sorted(cells):
            rows = cells[key]
            while pointers[key] < len(rows):
                cand = rows[pointers[key]]
                pointers[key] += 1
                if per_user[cand["group_id"]] >= per_user_cap or cand["id"] in seen_ids:
                    continue
                per_user[cand["group_id"]] += 1
                seen_ids.add(cand["id"])
                chosen.append(cand)
                progressed = True
                break
            if len(chosen) >= n_target:
                break
        if not progressed:
            break
    return pd.DataFrame(chosen).sort_values("id").reset_index(drop=True)


# --- batches ----------------------------------------------------------------------------------------------------

BATCH_README = """IRIS gold labelling batch
=========================

Read docs/LABELING_GUIDE.md first. Label every row: intent, urgency, subject, uncertain (0 or 1), optional notes.
Work alone and do not discuss items with the other annotator until adjudication.

Allowed values
  urgency  low | medium | high
  intent   emotional_support | stress | crisis | other
  subject  self | third_party | unclear
  uncertain  0 or 1 (1 = you are genuinely unsure; when torn, choose the HIGHER urgency)

Some rows appear twice (the second copy has an id ending in ~r). Label each on its own; do not look back at your earlier
answer. This lets us measure how consistent each annotator is.

Your wellbeing: this text can be distressing. Work in sessions of at most 45 minutes, take breaks, do not label late at
night or alone, and stop any time without giving a reason. If something affects you, tell the project lead.
Do not copy or share any text outside this file.
"""


def write_batches(pool: pd.DataFrame, out_dir: Path, seed: int = 2026, repeat_fraction: float = 0.1,
                  annotators: tuple[str, ...] = ("A", "B")) -> dict[str, Path]:
    """One blind CSV per annotator: same items, different order, no hidden columns, ~10% repeats for consistency."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    base = pool[["id", "text"]]
    for who in annotators:
        reps = base.sample(frac=repeat_fraction, random_state=int(_hash(seed, who)[:8], 16)).copy()
        reps["id"] = reps["id"] + REPEAT_SUFFIX
        batch = pd.concat([base, reps], ignore_index=True)
        batch = batch.sample(frac=1.0, random_state=int(_hash(seed, "order" + who)[:8], 16)).reset_index(drop=True)
        for col in LABEL_COLUMNS:
            batch[col] = ""
        paths[who] = out_dir / f"annotator_{who}.csv"
        batch[ANNOTATOR_COLUMNS].to_csv(paths[who], index=False)
    (out_dir / "README.txt").write_text(BATCH_README, encoding="utf-8")
    return paths


# --- ingesting labelled batches ---------------------------------------------------------------------------------

def load_annotations(path: Path, pool_ids: set[str]) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Returns (main labels, repeat labels, problems). A non-empty problem list means the file is not ready."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    problems: list[str] = []
    if [c for c in ANNOTATOR_COLUMNS if c not in df.columns]:
        return df, df.iloc[0:0], [f"{Path(path).name}: missing columns"]
    for c in ["intent", "urgency", "subject"]:
        df[c] = df[c].str.strip().str.lower()
    df["uncertain"] = df["uncertain"].str.strip().replace({"": "0"})
    for col, allowed in (("urgency", URGENCY), ("intent", INTENT), ("subject", SUBJECT)):
        bad = ~df[col].isin(allowed)
        if bad.any():
            problems.append(f"{Path(path).name}: {int(bad.sum())} rows with a missing or invalid {col}")
    if (~df["uncertain"].isin(["0", "1"])).any():
        problems.append(f"{Path(path).name}: 'uncertain' must be 0 or 1")
    if df["id"].duplicated().any():
        problems.append(f"{Path(path).name}: duplicate ids")
    if ((df["intent"] == "crisis") & (df["urgency"] == "low")).any():
        problems.append(f"{Path(path).name}: intent=crisis with urgency=low (crisis must be at least medium)")
    if ((df["urgency"] == "high") & (df["intent"] != "crisis")).any():
        problems.append(f"{Path(path).name}: urgency=high with an intent other than crisis")
    is_rep = df["id"].str.endswith(REPEAT_SUFFIX)
    main, reps = df[~is_rep].copy(), df[is_rep].copy()
    reps["id"] = reps["id"].str[: -len(REPEAT_SUFFIX)]
    missing, extra = pool_ids - set(main["id"]), set(main["id"]) - pool_ids
    if missing:
        problems.append(f"{Path(path).name}: {len(missing)} items not labelled")
    if extra:
        problems.append(f"{Path(path).name}: {len(extra)} ids that are not in the pool")
    return main.reset_index(drop=True), reps.reset_index(drop=True), problems


def intra_annotator_kappa(main: pd.DataFrame, reps: pd.DataFrame) -> dict:
    m = main.merge(reps, on="id", suffixes=("_1", "_2"))
    if len(m) < 5:
        return {"n_repeats": int(len(m)), "urgency_kappa": float("nan"), "intent_kappa": float("nan")}
    idx = {u: i for i, u in enumerate(URGENCY)}
    return {"n_repeats": int(len(m)),
            "urgency_kappa": cohens_kappa(m["urgency_1"].map(idx), m["urgency_2"].map(idx), weights="quadratic"),
            "intent_kappa": cohens_kappa(m["intent_1"], m["intent_2"])}


def adjudication_sheet(a: pd.DataFrame, b: pd.DataFrame, pool: pd.DataFrame) -> pd.DataFrame:
    """Items the annotators disagree on, High first, with empty 'final_*' columns for the counsellor to fill."""
    q = to_adjudicate(a, b).merge(pool[["id", "text"]], on="id", how="left")
    cols = ["id", "text", "urgency_a", "urgency_b", "intent_a", "intent_b", "involves_high"]
    q = q[cols].copy()
    for c in ("final_intent", "final_urgency", "final_subject", "adjudicator_notes"):
        q[c] = ""
    return q


def finalize(a: pd.DataFrame, b: pd.DataFrame, adjudicated: pd.DataFrame, pool: pd.DataFrame,
             heldout_groups: set[str]) -> pd.DataFrame:
    """Combine: where both annotators agree use that label; otherwise the counsellor's. Validates before returning."""
    m = a.merge(b, on="id", suffixes=("_a", "_b"))
    adj = adjudicated.set_index("id") if len(adjudicated) else pd.DataFrame(columns=["final_intent", "final_urgency", "final_subject"]).set_index(pd.Index([], name="id"))
    rows = []
    for _, r in m.iterrows():
        agree = r["urgency_a"] == r["urgency_b"] and r["intent_a"] == r["intent_b"]
        if agree:
            intent, urgency = r["intent_a"], r["urgency_a"]
            subject = r["subject_a"] if r["subject_a"] == r["subject_b"] else "unclear"
            how = "agreed"
        else:
            if r["id"] not in adj.index or not str(adj.loc[r["id"], "final_urgency"]).strip() or not str(adj.loc[r["id"], "final_intent"]).strip():
                raise ValueError(f"{r['id']}: annotators disagree and the counsellor has not adjudicated it")
            intent = str(adj.loc[r["id"], "final_intent"]).strip().lower()
            urgency = str(adj.loc[r["id"], "final_urgency"]).strip().lower()
            subject = (str(adj.loc[r["id"], "final_subject"]).strip().lower() or "unclear")
            how = "adjudicated"
        rows.append({"id": r["id"], "intent": intent, "urgency": urgency, "subject": subject, "resolution": how,
                     "uncertain": int(r["uncertain_a"] == "1" or r["uncertain_b"] == "1")})
    gold = pd.DataFrame(rows).merge(pool[["id", "text", "group_id"]], on="id", validate="one_to_one")
    gold["source"], gold["split"], gold["is_synthetic"] = SOURCE, "test", False
    if not set(gold["group_id"]) <= set(heldout_groups):
        raise ValueError("gold items must come only from held-out test users")
    assert_valid(gold)
    return gold.sort_values("id").reset_index(drop=True)


# --- freezing ---------------------------------------------------------------------------------------------------

def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(gold: pd.DataFrame, directory: Path, name: str = "gold_v1", force: bool = False) -> dict:
    """Write the gold file and record its hash. Once frozen it cannot be rewritten without an explicit force."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    csv, record = directory / f"{name}.csv", directory / "GOLD_FREEZE.json"
    if record.exists() and not force:
        raise FileExistsError("the gold set is already frozen; it must not change after models are tuned against it")
    gold.to_csv(csv, index=False)
    info = {"file": csv.name, "sha256": file_sha256(csv), "n": int(len(gold)),
            "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "urgency_counts": {u: int((gold["urgency"] == u).sum()) for u in URGENCY},
            "intent_counts": {i: int((gold["intent"] == i).sum()) for i in INTENT}}
    record.write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


def verify_frozen(directory: Path) -> dict:
    """Raise if the gold file no longer matches its recorded hash. Evaluation code should call this first."""
    directory = Path(directory)
    record = directory / "GOLD_FREEZE.json"
    if not record.exists():
        raise FileNotFoundError("the gold set has not been frozen yet")
    info = json.loads(record.read_text(encoding="utf-8"))
    if file_sha256(directory / info["file"]) != info["sha256"]:
        raise RuntimeError("the gold file has been modified since it was frozen")
    return info


def native_crosstab(gold: pd.DataFrame, pool: pd.DataFrame) -> pd.DataFrame:
    """Sanity check for later: gold urgency vs the psychiatrists' per-user label of the same users."""
    return pd.crosstab(pool.set_index("id").loc[gold["id"], "native_label"].values, gold["urgency"].values)


# --- command line -----------------------------------------------------------------------------------------------

def _heldout() -> tuple[pd.DataFrame, set[str]]:
    from .datasets import reddit_cssrs as rc
    df = rc.to_frame(rc.load_raw())
    rc.verify_manifest(df)
    test = df[df["split"] == "test"].reset_index(drop=True)
    return test, set(test["group_id"])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "check", "finalize"])
    ap.add_argument("--dir", default=str(GOLD_DIR))
    ap.add_argument("--n", type=int, default=N_TARGET)
    args = ap.parse_args(argv)
    d = Path(args.dir)
    ann = d / "annotations"
    if args.command == "build":
        test, _ = _heldout()
        pool = build_pool(test, n_target=args.n)
        pool.to_csv(d / "pool_private.csv", index=False)  # keeps hidden columns; NEVER give this file to annotators
        write_batches(pool, d / "batches")
        print(f"pool: {len(pool)} segments from {pool['group_id'].nunique()} held-out users")
        print("strata:\n" + pool["stratum"].value_counts().sort_index().to_string())
        print(f"batches written to {d / 'batches'} (annotator_A.csv, annotator_B.csv); give each annotator ONLY their own file")
        return
    pool = pd.read_csv(d / "pool_private.csv")
    ids = set(pool["id"])
    a, ra, pa = load_annotations(ann / "annotator_A.csv", ids)
    b, rb, pb = load_annotations(ann / "annotator_B.csv", ids)
    if pa + pb:
        raise SystemExit("not ready:\n  - " + "\n  - ".join(pa + pb))
    if args.command == "check":
        print(json.dumps({"agreement": compare(a, b), "annotator_A_consistency": intra_annotator_kappa(a, ra),
                          "annotator_B_consistency": intra_annotator_kappa(b, rb)}, indent=1, default=float))
        sheet = adjudication_sheet(a, b, pool)
        sheet.to_csv(ann / "adjudication_sheet.csv", index=False)
        print(f"{len(sheet)} items need the counsellor ({int(sheet['involves_high'].sum())} involve High): {ann / 'adjudication_sheet.csv'}")
        return
    adj_path = ann / "adjudication_sheet.csv"
    adj = pd.read_csv(adj_path, dtype=str, keep_default_na=False) if adj_path.exists() else pd.DataFrame()
    _, heldout = _heldout()
    gold = finalize(a, b, adj, pool, heldout)
    print(json.dumps(freeze(gold, d), indent=1))


if __name__ == "__main__":
    main()
