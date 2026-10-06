"""Tests for the gold-set workflow, on synthetic documents only."""
import json

import numpy as np
import pandas as pd
import pytest

from iris_ml import gold
from iris_ml.datasets import reddit_cssrs as rc

LABELS = ["Supportive", "Indicator", "Ideation", "Behavior", "Attempt"]


def sentence(i, kind):
    base = (f"Lately I have been thinking a lot about how everything at home and at school keeps piling up number {i} "
            "and I honestly do not know who to talk to about it anymore")
    extra = {"plain": ".", "review": " and sometimes I want to die.", "high": " and I am going to kill myself tonight."}[kind]
    return base + extra


def fake_test_docs(users_per_label=4):
    rows = []
    for l_i, label in enumerate(LABELS):
        for u in range(users_per_label):
            kinds = ["plain"] * 8 + (["review"] * 3 if l_i >= 2 else []) + (["high"] * 2 if l_i >= 3 else [])
            text = " ".join(sentence(l_i * 1000 + u * 50 + k, kind) for k, kind in enumerate(kinds))
            rows.append({"id": f"rc-{label}-{u}", "group_id": f"rc-{label}-{u}", "text": text, "native_label": label,
                         "split": "test"})
    return pd.DataFrame(rows)


@pytest.fixture()
def pool():
    return gold.build_pool(fake_test_docs(), n_target=40, per_user_cap=3, seed=7)


# --- sampling ---------------------------------------------------------------------------------------------------

def test_pool_only_from_held_out_users():
    docs = fake_test_docs()
    docs.loc[0, "split"] = "train"
    with pytest.raises(ValueError, match="held-out"):
        gold.build_pool(docs)


def test_pool_respects_size_cap_uniqueness_and_is_deterministic(pool):
    assert 0 < len(pool) <= 40 and pool["id"].is_unique
    assert pool.groupby("group_id").size().max() <= 3
    again = gold.build_pool(fake_test_docs(), n_target=40, per_user_cap=3, seed=7)
    assert pool.equals(again)
    other = gold.build_pool(fake_test_docs(), n_target=40, per_user_cap=3, seed=8)
    assert not pool["id"].equals(other["id"]) or not pool["text"].equals(other["text"])


def test_pool_covers_hard_cases_on_both_sides(pool):
    strata = set(pool["stratum"])
    assert any(s.startswith("Supportive|none") for s in strata)
    assert any("|high|" in s for s in strata) and any("|review|" in s for s in strata)
    assert pool["native_label"].nunique() == 5                       # every psychiatrist label is represented


def test_english_like_filter():
    assert gold.english_like(sentence(1, "plain"))
    assert not gold.english_like("too short to be useful")
    assert not gold.english_like(("नमस्ते " * 30))                          # not English
    assert not gold.english_like(("see <url> and <url> " * 10) + "word " * 20)                           # link wall


# --- batches ----------------------------------------------------------------------------------------------------

def test_batches_are_blind_complete_and_independent(pool, tmp_path):
    paths = gold.write_batches(pool, tmp_path, seed=3, repeat_fraction=0.1)
    a, b = pd.read_csv(paths["A"], dtype=str, keep_default_na=False), pd.read_csv(paths["B"], dtype=str, keep_default_na=False)
    for df in (a, b):
        assert list(df.columns) == gold.ANNOTATOR_COLUMNS                   # no native_label / rule columns leak to annotators
        assert (df[gold.LABEL_COLUMNS] == "").all().all()                   # nothing is pre-labelled
        main_ids = set(df[~df["id"].str.endswith(gold.REPEAT_SUFFIX)]["id"])
        assert main_ids == set(pool["id"])
        assert df["id"].str.endswith(gold.REPEAT_SUFFIX).sum() == round(len(pool) * 0.1)
    assert list(a["id"]) != list(b["id"])                                   # different order for each annotator
    assert "wellbeing" in (tmp_path / "README.txt").read_text(encoding="utf-8")


def annotate(path, rule):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for i, r in df.iterrows():
        intent, urgency = rule(r["id"].removesuffix(gold.REPEAT_SUFFIX), r["text"])
        df.loc[i, ["intent", "urgency", "subject", "uncertain"]] = [intent, urgency, "self", "0"]
    df.to_csv(path, index=False)
    return df


def by_text(id_, text):
    if "kill myself" in text:
        return "crisis", "high"
    if "want to die" in text:
        return "crisis", "medium"
    return "stress", "low"


@pytest.fixture()
def labelled(pool, tmp_path):
    paths = gold.write_batches(pool, tmp_path, seed=3, repeat_fraction=0.25)   # enough repeats for a consistency kappa
    annotate(paths["A"], by_text)
    annotate(paths["B"], by_text)
    return pool, paths


def test_clean_annotations_load_without_problems(labelled):
    pool, paths = labelled
    main, reps, problems = gold.load_annotations(paths["A"], set(pool["id"]))
    assert problems == [] and len(main) == len(pool) and len(reps) > 0
    k = gold.intra_annotator_kappa(main, reps)
    assert k["urgency_kappa"] == pytest.approx(1.0) and k["n_repeats"] == len(reps)


def test_incomplete_or_invalid_annotations_are_rejected(labelled):
    pool, paths = labelled
    df = pd.read_csv(paths["A"], dtype=str, keep_default_na=False)
    df.loc[0, "urgency"] = "urgent"          # invalid value
    df.loc[1, "intent"] = ""                 # missing value
    df = df.iloc[:-5]                        # items left unlabelled
    df.to_csv(paths["A"], index=False)
    _, _, problems = gold.load_annotations(paths["A"], set(pool["id"]))
    text = " | ".join(problems)
    assert "invalid urgency" in text and "invalid intent" in text and "not labelled" in text


def test_clinical_consistency_rules_apply_to_annotations(labelled):
    pool, paths = labelled
    df = pd.read_csv(paths["A"], dtype=str, keep_default_na=False)
    df.loc[0, ["intent", "urgency"]] = ["crisis", "low"]
    df.loc[1, ["intent", "urgency"]] = ["stress", "high"]
    df.to_csv(paths["A"], index=False)
    _, _, problems = gold.load_annotations(paths["A"], set(pool["id"]))
    assert any("crisis must be at least medium" in p for p in problems) and any("urgency=high" in p for p in problems)


# --- adjudication and finalising -------------------------------------------------------------------------------------

def disagree_on_some(id_, text):
    intent, urgency = by_text(id_, text)
    if urgency == "high" and int(id_[-1], 16) % 2 == 0:       # annotator B downgrades some High items
        return "crisis", "medium"
    return intent, urgency


def test_adjudication_is_required_for_every_disagreement(pool, tmp_path):
    paths = gold.write_batches(pool, tmp_path, seed=3)
    annotate(paths["A"], by_text)
    annotate(paths["B"], disagree_on_some)
    a, _, pa = gold.load_annotations(paths["A"], set(pool["id"]))
    b, _, pb = gold.load_annotations(paths["B"], set(pool["id"]))
    assert pa == [] and pb == []
    sheet = gold.adjudication_sheet(a, b, pool)
    assert len(sheet) > 0 and sheet["involves_high"].all() and (sheet["final_urgency"] == "").all()
    groups = set(pool["group_id"])
    with pytest.raises(ValueError, match="has not adjudicated"):
        gold.finalize(a, b, sheet, pool, groups)                  # blank 'final_*' columns are not accepted
    sheet["final_intent"], sheet["final_urgency"], sheet["final_subject"] = "crisis", "high", "self"
    final = gold.finalize(a, b, sheet, pool, groups)
    assert len(final) == len(pool) and set(final["split"]) == {"test"} and not final["is_synthetic"].any()
    assert set(final.loc[final["id"].isin(sheet["id"]), "resolution"]) == {"adjudicated"}
    assert set(final.loc[~final["id"].isin(sheet["id"]), "resolution"]) == {"agreed"}
    assert (final.loc[final["id"].isin(sheet["id"]), "urgency"] == "high").all()


def test_gold_from_non_heldout_users_is_refused(labelled):
    pool, paths = labelled
    a, _, _ = gold.load_annotations(paths["A"], set(pool["id"]))
    b, _, _ = gold.load_annotations(paths["B"], set(pool["id"]))
    with pytest.raises(ValueError, match="held-out"):
        gold.finalize(a, b, pd.DataFrame(), pool, heldout_groups={"some-other-user"})


def test_perfect_agreement_needs_no_adjudication(labelled):
    pool, paths = labelled
    a, _, _ = gold.load_annotations(paths["A"], set(pool["id"]))
    b, _, _ = gold.load_annotations(paths["B"], set(pool["id"]))
    assert len(gold.adjudication_sheet(a, b, pool)) == 0
    final = gold.finalize(a, b, pd.DataFrame(), pool, set(pool["group_id"]))
    assert set(final["resolution"]) == {"agreed"}


# --- freezing ---------------------------------------------------------------------------------------------------

def make_gold(pool):
    g = pool[["id", "text", "group_id"]].copy()
    g["intent"], g["urgency"], g["subject"] = "stress", "low", "self"
    g["source"], g["split"], g["is_synthetic"] = gold.SOURCE, "test", False
    return g


def test_freeze_records_hash_and_cannot_be_overwritten(pool, tmp_path):
    info = gold.freeze(make_gold(pool), tmp_path)
    assert info["n"] == len(pool) and info["urgency_counts"]["low"] == len(pool)
    assert gold.verify_frozen(tmp_path)["sha256"] == info["sha256"]
    with pytest.raises(FileExistsError, match="already frozen"):
        gold.freeze(make_gold(pool), tmp_path)
    gold.freeze(make_gold(pool), tmp_path, force=True)               # only possible by deliberate choice


def test_tampering_with_the_frozen_file_is_detected(pool, tmp_path):
    gold.freeze(make_gold(pool), tmp_path)
    csv = tmp_path / "gold_v1.csv"
    csv.write_text(csv.read_text(encoding="utf-8").replace("stress", "crisis", 1), encoding="utf-8")
    with pytest.raises(RuntimeError, match="modified"):
        gold.verify_frozen(tmp_path)


def test_verify_before_freezing_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError):
        gold.verify_frozen(tmp_path)


def test_risk_vocabulary_is_a_sampling_aid_and_never_a_label():
    assert gold.has_signal("I took the pills and woke up in the hospital") and gold.has_signal("I have a plan for tonight")
    assert not gold.has_signal("I had a nice walk and talked to my sister about school")
    pool = gold.build_pool(fake_test_docs(), n_target=30, per_user_cap=3, seed=1)
    assert "signal" in pool.columns and not {"urgency", "intent"} & set(pool.columns)        # no label columns anywhere
