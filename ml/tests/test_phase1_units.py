"""Unit tests for the Phase 1 pieces. They use small fake datasets, never the real Reddit text."""
import json

import numpy as np
import pandas as pd
import pytest

from iris_ml import baselines, calibration, schema, segment
from iris_ml.datasets import reddit_cssrs as rc
from iris_ml.splits import stratified_group_split

LABELS = rc.NATIVE_ORDER


def fake_raw(n_per_class=12, seed=0):
    rng = np.random.default_rng(seed)
    vocab = {l: [f"{l.lower()}word{i}" for i in range(6)] for l in LABELS}
    rows = []
    for l in LABELS:
        for i in range(n_per_class):
            words = list(rng.choice(vocab[l], 25)) + list(rng.choice(["the", "and", "feel", "today", "just"], 15))
            rows.append({"User": f"user_{l}_{i}", "Post": " ".join(words), "Label": l})
    return pd.DataFrame(rows)


# --- loader -----------------------------------------------------------------------------------------------------

def test_clean_text_masks_links_and_mentions_and_collapses_whitespace():
    t = rc.clean_text("see https://example.com/x?y=1  and www.foo.org, thanks u/some_user and /u/Other-1\n\nbye")
    assert "http" not in t and "www." not in t and "some_user" not in t and "Other-1" not in t
    assert "<url>" in t and "<user>" in t and "\n" not in t and "  " not in t


def test_user_ids_are_one_way_hashed():
    h = rc.user_hash("some_real_username")
    assert h.startswith("rc-") and "some_real_username" not in h and len(h) == 15 and h == rc.user_hash("some_real_username")


def test_to_frame_validates_and_maps_labels_under_both_variants():
    raw = fake_raw()
    cons, lenient = rc.to_frame(raw, "conservative"), rc.to_frame(raw, "lenient")
    for df in (cons, lenient):
        schema.assert_valid(df, max_chars=rc.MAX_DOC_CHARS)
    assert set(cons.loc[cons.native_label == "Indicator", "urgency"]) == {"medium"}
    assert set(lenient.loc[lenient.native_label == "Indicator", "urgency"]) == {"low"}
    assert set(cons.loc[cons.native_label.isin(["Behavior", "Attempt"]), "urgency"]) == {"high"}
    assert set(cons.loc[cons.native_label == "Supportive", "urgency"]) == {"low"}
    assert (cons["split"] == lenient["split"]).all()          # the held-out users never depend on the mapping
    assert not cons["is_synthetic"].any() and (cons["intent"][cons.urgency == "high"] == "crisis").all()


def test_split_is_stratified_and_keeps_every_class_in_every_split():
    df = rc.to_frame(fake_raw(n_per_class=20))
    table = pd.crosstab(df["native_label"], df["split"])
    assert (table > 0).all().all()
    assert table.loc["Attempt", "test"] in (3,)               # 15% of 20


def test_loader_rejects_bad_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        rc.load_raw(tmp_path / "missing.csv")
    p = tmp_path / "bad.csv"
    p.write_text("User,Text,Label\na,b,Attempt\n")
    with pytest.raises(ValueError, match="columns"):
        rc.load_raw(p)
    p.write_text("User,Post,Label\na,b,Mystery\n")
    with pytest.raises(ValueError, match="unknown labels"):
        rc.load_raw(p)
    p.write_text("User,Post,Label\na,b,Attempt\na,c,Attempt\n")
    with pytest.raises(ValueError, match="one row per user"):
        rc.load_raw(p)


def test_manifest_roundtrip_and_tamper_detection(tmp_path):
    df = rc.to_frame(fake_raw())
    path = tmp_path / "m.csv"
    digest = rc.write_manifest(df, path)
    rc.verify_manifest(df, path)
    assert digest == rc.manifest_sha256(rc.split_manifest(df))
    tampered = df.copy()
    tampered.loc[tampered.index[0], "split"] = "test" if tampered.loc[tampered.index[0], "split"] != "test" else "train"
    with pytest.raises(RuntimeError, match="no longer matches"):
        rc.verify_manifest(tampered, path)


def test_stratified_split_is_deterministic_and_seed_dependent():
    g = pd.Series([f"g{i}" for i in range(100)])
    s = pd.Series(["a"] * 50 + ["b"] * 50)
    one = stratified_group_split(g, s, seed=1)
    assert one.equals(stratified_group_split(g, s, seed=1)) and not one.equals(stratified_group_split(g, s, seed=2))
    counts = one.value_counts()                                  # 15% of a 50-row stratum is 7.5, which rounds up per stratum
    assert abs(counts["train"] - 70) <= 2 and abs(counts["val"] - 15) <= 2 and abs(counts["test"] - 15) <= 2 and counts.sum() == 100
    for stratum in ("a", "b"):                                   # identical proportions in each stratum
        assert one[s == stratum].value_counts().to_dict() == one[s == "a"].value_counts().to_dict()
    with pytest.raises(ValueError):
        stratified_group_split(pd.Series(["x", "x"]), pd.Series(["a", "a"]))


# --- segmenting -------------------------------------------------------------------------------------------------

def test_windows_respect_length_and_do_not_lose_text_order():
    text = " ".join(f"This is sentence number {i} and it has a few words in it." for i in range(40))
    ws = segment.windows(text, min_chars=100, max_chars=300, max_sentences=3)
    assert ws and all(100 <= len(w) <= 300 for w in ws)
    joined = " ".join(ws)
    assert joined.index("number 0 ") < joined.index("number 20 ")


def test_windows_handles_punctuation_free_run_ons_and_short_texts():
    run_on = "word " * 400
    assert all(len(w) <= 600 for w in segment.windows(run_on))
    assert segment.windows("too short") == []
    assert segment.windows("") == []


# --- calibration ------------------------------------------------------------------------------------------------

def test_temperature_one_is_identity_and_rows_sum_to_one():
    p = np.array([[0.7, 0.2, 0.1], [0.1, 0.1, 0.8]])
    assert np.allclose(calibration.apply_temperature(p, 1.0), p)
    assert np.allclose(calibration.apply_temperature(p, 2.5).sum(axis=1), 1.0)
    assert calibration.apply_temperature(p, 3.0).max() < p.max()          # T > 1 softens


def test_fit_temperature_detects_over_and_under_confidence():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 600)
    # a model that is always 95% sure but right only ~50% of the time is over-confident -> T > 1
    over = np.full((600, 3), 0.025)
    guess = np.where(rng.random(600) < 0.5, y, rng.integers(0, 3, 600))
    over[np.arange(600), guess] = 0.95
    assert calibration.fit_temperature(over, y) > 1.5
    # a model that is 40% sure but always right is under-confident -> T < 1
    under = np.full((600, 3), 0.3)
    under[np.arange(600), y] = 0.4
    assert calibration.fit_temperature(under, y) < 0.7


def test_crossfit_never_uses_the_held_out_fold_and_lowers_ece():
    from iris_ml.metrics import ece
    rng = np.random.default_rng(1)
    y = rng.integers(0, 3, 900)
    probs = np.full((900, 3), 0.02)
    probs[np.arange(900), np.where(rng.random(900) < 0.55, y, rng.integers(0, 3, 900))] = 0.96
    folds = np.arange(900) % 5
    cal, temps = calibration.crossfit_temperature(probs, y, folds)
    assert set(temps) == {0, 1, 2, 3, 4} and np.allclose(cal.sum(axis=1), 1.0)
    assert ece(cal, y) < ece(probs, y)


# --- baselines --------------------------------------------------------------------------------------------------

def test_m1_learns_a_separable_toy_problem_and_oof_covers_everyone():
    df = rc.to_frame(fake_raw())
    y = df["urgency"].map({"low": 0, "medium": 1, "high": 2}).to_numpy()
    cfg = baselines.BaselineConfig(n_splits=3, n_repeats=2, max_features=2000)
    raw, cal, temp = baselines.oof_probabilities(df["text"], y, 3, cfg)
    assert raw.shape == cal.shape == (len(df), 3) and np.allclose(raw.sum(axis=1), 1.0) and np.allclose(cal.sum(axis=1), 1.0)
    assert (cal.argmax(axis=1) == y).mean() > 0.9 and temp > 0


def test_training_on_the_test_split_is_refused():
    df = rc.to_frame(fake_raw())
    with pytest.raises(RuntimeError, match="test split"):
        baselines.assert_no_test(df)
    baselines.assert_no_test(df[df["split"] != "test"])


def test_trivial_baselines_behave():
    y = np.array([0] * 70 + [1] * 20 + [2] * 10)
    assert (baselines.majority_prediction(y) == 0).all()
    r = baselines.stratified_random_prediction(y, seed=3)
    assert len(r) == 100 and set(r) <= {0, 1, 2}
    pred = baselines.rules_prediction(pd.Series(["I am going to kill myself tonight", "I want to die", "nice weather"]))
    assert list(pred) == [2, 1, 0]


def test_end_to_end_runner_writes_a_report_without_leaking_text(tmp_path, monkeypatch):
    from iris_ml import ROOT, run_phase1
    real_manifest = ROOT / "data" / "splits" / "reddit_cssrs_v1.csv"
    existed_before = real_manifest.exists()
    raw = fake_raw(n_per_class=15)
    raw_path = tmp_path / "raw.csv"
    raw.to_csv(raw_path, index=False)
    manifest = tmp_path / "manifest.csv"
    monkeypatch.setattr(rc, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(run_phase1, "ARTIFACTS", tmp_path / "artifacts")
    run_phase1.main(["--write-manifest", "--raw", str(raw_path), "--out", str(tmp_path / "out")])
    report = (tmp_path / "out" / "phase1_baseline.md").read_text(encoding="utf-8")
    metrics = json.loads((tmp_path / "out" / "phase1_metrics.json").read_text(encoding="utf-8"))
    assert "Read this first" in report and "test users were not touched" in report
    assert set(metrics["results"]) == {"conservative", "lenient"}
    for post in raw["Post"].head(5):                                   # no raw text leaks into the report
        assert post[:60] not in report
    assert (tmp_path / "artifacts" / "pipeline.joblib").exists()
    assert manifest.exists()                                            # the redirected manifest was the one written
    assert real_manifest.exists() == existed_before                     # regression: tests must never touch the real one
