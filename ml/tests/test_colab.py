"""Tests for the Colab packaging: no GPU, no fine-tuning, no dataset text needed."""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

ML = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML / "colab"))

import build_bundle as bb          # noqa: E402
import colab_finetune as cf        # noqa: E402
import ingest_results as ing       # noqa: E402
from iris_ml import provenance     # noqa: E402
from test_experiments import toy_prep  # noqa: E402


# --- the plan is exactly the project's registered fine-tuning experiments ------------------------------------------------------

def test_plan_matches_the_registered_finetune_experiments():
    p = cf.plan(["conservative", "lenient"])
    assert [(v, s.name) for v, s in p] == [("conservative", "e3_distilroberta_ft"), ("conservative", "e3s_distilroberta_ft_syn"),
                                           ("conservative", "e3o_distilroberta_ft_ordinal"), ("lenient", "e3_distilroberta_ft")]
    assert all(s.family == "finetune" and s.repeats == 1 for _, s in p)


def test_the_cli_never_fine_tunes_without_explicit_opt_in(monkeypatch):
    from iris_ml import run_phase2
    monkeypatch.delenv("IRIS_ALLOW_FINETUNE", raising=False)
    assert run_phase2._finetune_allowed() is False


# --- fingerprint -----------------------------------------------------------------------------------------------------------------

def test_fingerprint_is_deterministic_and_detects_any_change():
    a, b = provenance.fingerprint(toy_prep()), provenance.fingerprint(toy_prep())
    assert a == b and "text" not in json.dumps(a)
    relabelled = toy_prep()
    relabelled.y[0] = (relabelled.y[0] + 1) % 3
    assert provenance.fingerprint(relabelled)["labels_sha256"] != a["labels_sha256"]
    edited = toy_prep()
    edited.chunks.loc[edited.chunks.index[0], "text"] += " x"
    assert provenance.fingerprint(edited)["chunks_sha256"] != a["chunks_sha256"]
    fewer = toy_prep(n_per_class=12)
    assert provenance.fingerprint(fewer)["folds_sha256"] != a["folds_sha256"]


def test_code_hash_changes_when_code_changes(tmp_path):
    (tmp_path / "iris_ml").mkdir()
    (tmp_path / "configs").mkdir()
    (tmp_path / "iris_ml" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "configs" / "c.yaml").write_text("a: 1\n", encoding="utf-8")
    h1 = provenance.code_sha256(tmp_path)
    assert h1 == provenance.code_sha256(tmp_path)
    (tmp_path / "iris_ml" / "m.py").write_text("x = 2\n", encoding="utf-8")
    assert provenance.code_sha256(tmp_path) != h1


# --- bundle ----------------------------------------------------------------------------------------------------------------------

def _fake_root(tmp_path: Path) -> Path:
    r = tmp_path / "ml"
    files = ["iris_ml/__init__.py", "iris_ml/datasets/reddit_cssrs.py", "iris_ml/__pycache__/x.cpython-311.pyc",
             "configs/labels.yaml", "data/splits/reddit_cssrs_v1.csv", "colab/colab_finetune.py",
             "data/raw/reddit_cssrs/500_Reddit_users_posts_labels.csv", "data/raw/reddit_cssrs/suicidal_attempt.csv",
             "data/raw/esconv/ESConv.json", "data/gold/blind.csv", "tests/test_x.py", "artifacts/phase2/a.npz", "reports/r.md"]
    for f in files:
        (r / f).parent.mkdir(parents=True, exist_ok=True)
        (r / f).write_text("x", encoding="utf-8")
    return r


def test_bundle_has_what_training_needs_and_nothing_else(tmp_path):
    root = _fake_root(tmp_path)
    z = bb.write_bundle(root, tmp_path / "b.zip", {"m": 1}, include_esconv=False)
    names = set(zipfile.ZipFile(z).namelist())
    assert {"ml/iris_ml/__init__.py", "ml/iris_ml/datasets/reddit_cssrs.py", "ml/configs/labels.yaml", "ml/data/splits/reddit_cssrs_v1.csv",
            "ml/data/raw/reddit_cssrs/500_Reddit_users_posts_labels.csv", "ml/colab/colab_finetune.py", "ml/colab_manifest.json",
            "ml/requirements-colab.txt"} <= names
    assert not any(n.startswith(("ml/data/gold", "ml/tests", "ml/artifacts", "ml/reports")) or "__pycache__" in n for n in names)
    assert "ml/data/raw/esconv/ESConv.json" not in names                       # restricted licence: only on request
    assert "ml/data/raw/reddit_cssrs/suicidal_attempt.csv" not in names
    with_esc = bb.write_bundle(root, tmp_path / "b2.zip", {"m": 1}, include_esconv=True)
    assert "ml/data/raw/esconv/ESConv.json" in zipfile.ZipFile(with_esc).namelist()


# --- ingest -----------------------------------------------------------------------------------------------------------------------

def _results(tmp_path: Path, fp: dict, name="e3_distilroberta_ft", key="abc123", n=5, bad=None) -> Path:
    d = tmp_path / "res"
    (d / "phase2").mkdir(parents=True)
    p = np.full((1, n, 3), 1 / 3)
    if bad == "nan":
        p[0, 0, 0] = np.nan
    np.savez(d / "phase2" / f"conservative_{name}_{key}.npz", raw=p, cal=p, risk=np.zeros((1, n)), temps=np.ones(5), seconds=1.0)
    np.savez(d / "phase2" / f"audit_conservative_{name}_{key}.npz", probs=np.full((7, 3), 1 / 3))
    (d / "colab_run.json").write_text(json.dumps({"fingerprints": {"conservative": fp}}), encoding="utf-8")
    return d


def test_ingest_accepts_matching_results_and_rejects_everything_else(tmp_path):
    fp = {"n_dev_users": 5, "folds_sha256": "f"}
    reg = {("conservative", "e3_distilroberta_ft"): "abc123"}
    ok = _results(tmp_path, fp)
    files = ing.check_and_collect(ok, {"conservative": fp}, reg, {"conservative": 5})
    assert [f.name for f in files] == ["audit_conservative_e3_distilroberta_ft_abc123.npz", "conservative_e3_distilroberta_ft_abc123.npz"]
    with pytest.raises(ing.IngestError, match="different data"):                                 # other split / labels
        ing.check_and_collect(ok, {"conservative": {**fp, "folds_sha256": "g"}}, reg, {"conservative": 5})
    with pytest.raises(ing.IngestError, match="registered experiment"):                          # spec changed since the run
        ing.check_and_collect(ok, {"conservative": fp}, {("conservative", "e3_distilroberta_ft"): "zzz"}, {"conservative": 5})
    with pytest.raises(ing.IngestError, match="wrong shape"):                                    # other number of users
        ing.check_and_collect(ok, {"conservative": fp}, reg, {"conservative": 6})
    import shutil
    shutil.rmtree(tmp_path / "res")
    nan = _results(tmp_path, fp, bad="nan")
    with pytest.raises(ing.IngestError, match="not valid probabilities|wrong shape"):
        ing.check_and_collect(nan, {"conservative": fp}, reg, {"conservative": 5})


# --- model persistence (needs the base model in the local cache; skipped otherwise, runs for real on Colab) -----------------------

def _model_cached() -> bool:
    try:
        from transformers import AutoTokenizer
        AutoTokenizer.from_pretrained("distilroberta-base", local_files_only=True)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _model_cached(), reason="distilroberta-base is not in the local cache")
def test_saved_finetuned_model_reloads_with_identical_probabilities(tmp_path):
    from iris_ml import neural
    texts = ["I am so happy and calm today"] * 8 + ["I am furious and everything is terrible"] * 8
    y = np.array([0] * 8 + [2] * 8)
    ft = neural.FineTuneScorer(neural.FTConfig(epochs=1, batch_size=8, max_len=16, seed=0, fp16=False)).fit(texts, y)
    probe = ["I am so happy and calm today", "I am furious and everything is terrible", "hello there"]
    before = ft.predict_proba(probe)
    ft.save(tmp_path / "m")
    after = neural.FineTuneScorer.load(tmp_path / "m").predict_proba(probe)
    assert np.allclose(before, after, atol=1e-4)
    assert not any(t in (tmp_path / "m" / "ft_config.json").read_text(encoding="utf-8") for t in ("happy", "furious"))
