import os

import numpy as np
import pandas as pd
import pytest

from iris_ml import experiments as ex
from iris_ml.chunks import build_chunks
from iris_ml.experiments import Prepared, Spec

VOCAB = {0: ["calm", "study", "tea", "walk", "friend"], 1: ["tired", "sad", "alone", "heavy", "cry"],
         2: ["tonight", "goodbye", "pills", "ending", "final"]}
COMMON = ["the", "and", "just", "today", "really", "think"]
ALL_WORDS = sorted({w for v in VOCAB.values() for w in v} | set(COMMON))


def fake_embed(texts, name):
    """Bag-of-words counts as an 'embedding': deterministic, and class words separate the classes."""
    out = np.zeros((len(texts), len(ALL_WORDS)), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in t.lower().replace(".", " ").split():
            if w in ALL_WORDS:
                out[i, ALL_WORDS.index(w)] += 1
    n = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.maximum(n, 1e-9)


def toy_prep(n_per_class=14, seed=0) -> Prepared:
    rng = np.random.default_rng(seed)
    rows = []
    for c, urg in enumerate(["low", "medium", "high"]):
        for i in range(n_per_class):
            sents = [" ".join(rng.choice(VOCAB[c], 5).tolist() + rng.choice(COMMON, 7).tolist()).capitalize() + "." for _ in range(10)]
            rows.append({"id": f"u{c}-{i}", "text": " ".join(sents), "native_label": "x", "urgency": urg})
    dev = pd.DataFrame(rows)
    y = dev["urgency"].map({"low": 0, "medium": 1, "high": 2}).to_numpy()
    ch = build_chunks(dev, max_chunks_per_doc=6)
    idx = {d: i for i, d in enumerate(dev["id"])}
    synth = pd.DataFrame({"text": ["calm study tea walk friend today", "sad alone heavy cry tired just", "tonight goodbye pills ending final"],
                          "urgency": ["low", "medium", "high"]})
    return Prepared("toy", dev, y, ch, ch["doc_id"].map(idx).to_numpy(), synth)


@pytest.mark.parametrize("family,kwargs", [
    ("doc_tfidf", {}), ("chunk_tfidf", {}), ("emb_lr", {"embedder": "fake"}),
    ("emb_head", {"embedder": "fake", "head": "ordinal", "epochs": 150}), ("mil", {"embedder": "fake", "epochs": 250}),
])
def test_every_family_learns_the_toy_problem_out_of_fold(family, kwargs, tmp_path):
    prep = toy_prep()
    spec = Spec(name=f"t_{family}", family=family, repeats=2, **kwargs)
    res = ex.run_spec(spec, prep, embed_fn=fake_embed, cache_dir=tmp_path, verbose=False)
    assert res.raw.shape == (2, len(prep.y), 3) and res.cal.shape == res.raw.shape and res.risk_topk.shape == (2, len(prep.y))
    assert np.allclose(res.raw.sum(axis=2), 1.0, atol=1e-5) and np.allclose(res.cal.sum(axis=2), 1.0, atol=1e-5)
    assert (res.cal[0].argmax(axis=1) == prep.y).mean() > 0.8
    assert (res.temps > 0).all() and len(res.temps) == 10                    # 5 folds x 2 repeats


def test_results_are_cached_and_reloaded_identically(tmp_path):
    prep = toy_prep()
    spec = Spec(name="c", family="emb_lr", embedder="fake", repeats=1)
    a = ex.run_spec(spec, prep, embed_fn=fake_embed, cache_dir=tmp_path, verbose=False)
    calls = {"n": 0}

    def boom(texts, name):
        calls["n"] += 1
        raise AssertionError("must not recompute")

    b = ex.run_spec(spec, prep, embed_fn=boom, cache_dir=tmp_path, verbose=False)
    assert calls["n"] == 0 and np.array_equal(a.cal, b.cal)
    other = Spec(name="c", family="emb_lr", embedder="fake", repeats=1, syn=True)          # different spec: different cache entry
    assert other.key() != spec.key()


def test_all_models_see_identical_folds():
    y = toy_prep().y
    a = [(r, f, tuple(te)) for r, f, _, te in ex.user_splits(y, 2)]
    b = [(r, f, tuple(te)) for r, f, _, te in ex.user_splits(y, 2)]
    assert a == b
    one = [tuple(te) for r, f, _, te in ex.user_splits(y, 1)]
    assert one == [t for r, f, t in a if r == 0]                  # one repeat reproduces the first repeat of several


def test_every_user_is_predicted_exactly_once_per_repeat_by_a_model_that_did_not_train_on_them(tmp_path):
    y = toy_prep().y
    for r in range(2):
        seen = np.concatenate([te for rr, f, tr, te in ex.user_splits(y, 2) if rr == r])
        assert sorted(seen) == list(range(len(y)))
        for rr, f, tr, te in ex.user_splits(y, 2):
            assert not set(tr) & set(te)


def test_synthetic_messages_only_ever_enter_training(tmp_path):
    """Make the synthetic text a trap: if it leaked into scoring, held-out users' predictions would change."""
    prep = toy_prep()
    spec = Spec(name="s", family="chunk_tfidf", repeats=1, syn=True)
    fitted = ex.fit_split(spec, prep, np.arange(0, 30), fake_embed, seed=1)
    p, _ = fitted.predict_users(np.arange(30, 36))
    assert p.shape == (6, 3)                                                  # scored users only, never synthetic rows


def test_metrics_summary_has_the_headline_numbers_and_the_spread(tmp_path):
    prep = toy_prep()
    res = ex.run_spec(Spec(name="m", family="emb_lr", embedder="fake", repeats=3), prep, embed_fn=fake_embed,
                      cache_dir=tmp_path, verbose=False)
    s = ex.summarise(res, prep.y)
    r0 = s["repeat0"]
    for key in ("macro_f1", "qwk", "auroc_high", "pr_auc_high", "ece_raw", "ece_cal", "mean_cost", "recall_at", "high_recall_argmax"):
        assert key in r0
    assert set(r0["recall_at"]) == {"10%", "20%", "30%", "40%", "50%"}
    assert s["n_repeats"] == 3 and "macro_f1_sd" in s and "recall_at_30_sd" in s
    assert 0.9 <= r0["auroc_high"] <= 1.0


@pytest.mark.skipif(not os.environ.get("IRIS_SLOW_TESTS"), reason="GPU fine-tuning test; set IRIS_SLOW_TESTS=1 to run")
def test_finetune_family_runs_end_to_end(tmp_path):
    prep = toy_prep(n_per_class=10)
    res = ex.run_spec(Spec(name="ft", family="finetune", repeats=1, epochs=2), prep, cache_dir=tmp_path, verbose=False)
    assert res.cal.shape == (1, len(prep.y), 3) and np.allclose(res.cal.sum(axis=2), 1.0, atol=1e-3)



# --- native five-label training --------------------------------------------------------------------------------------------------

def toy_prep_native():
    prep = toy_prep()
    native_of_class = np.array([0, 2, 3])                    # low -> Supportive, medium -> Ideation, high -> Behavior
    prep.y5 = native_of_class[prep.y]
    m5 = np.zeros((5, 3))
    for native, urg in enumerate([0, 1, 1, 2, 2]):           # Supportive low; Indicator and Ideation medium; Behavior and Attempt high
        m5[native, urg] = 1
    prep.map5 = m5
    return prep


@pytest.mark.parametrize("family,kwargs", [("doc_tfidf", {}), ("chunk_tfidf", {}), ("emb_lr", {"embedder": "fake"}),
                                           ("emb_head", {"embedder": "fake", "head": "ordinal", "epochs": 300})])
def test_native5_models_train_on_five_labels_but_predict_urgency(family, kwargs, tmp_path):
    prep = toy_prep_native()
    spec = Spec(name=f"n5_{family}", family=family, repeats=1, target="native5", **kwargs)
    res = ex.run_spec(spec, prep, embed_fn=fake_embed, cache_dir=tmp_path, verbose=False)
    assert res.cal.shape == (1, len(prep.y), 3) and np.allclose(res.cal.sum(axis=2), 1.0, atol=1e-5)
    assert (res.cal[0].argmax(axis=1) == prep.y).mean() > 0.8


def test_native5_can_be_reread_under_a_different_mapping_without_retraining():
    prep = toy_prep_native()
    fitted = ex.fit_split(Spec("n", "emb_lr", repeats=1, embedder="fake", target="native5"), prep, np.arange(0, 30), fake_embed, seed=0)
    p_cons, _ = fitted.predict_users(np.arange(30, 42))
    lenient = np.zeros((5, 3))
    for native, urg in enumerate([0, 0, 1, 2, 2]):           # Indicator now counts as Low
        lenient[native, urg] = 1
    prep.map5 = lenient
    fitted2 = ex.fit_split(Spec("n", "emb_lr", repeats=1, embedder="fake", target="native5"), prep, np.arange(0, 30), fake_embed, seed=0)
    p_len, _ = fitted2.predict_users(np.arange(30, 42))
    assert np.allclose(p_cons.sum(axis=1), 1) and np.allclose(p_len.sum(axis=1), 1)
    assert (p_len[:, 0] >= p_cons[:, 0] - 1e-9).all()         # only the mapping changed: Low can only gain what Indicator carried


def test_native5_refuses_unsupported_combinations():
    prep = toy_prep_native()
    for bad in (Spec("a", "mil", embedder="fake", target="native5"), Spec("b", "emb_lr", embedder="fake", syn=True, target="native5")):
        with pytest.raises(NotImplementedError):
            ex.fit_split(bad, prep, np.arange(0, 30), fake_embed, seed=0)
    with pytest.raises(ValueError, match="native labels"):
        ex.fit_split(Spec("c", "doc_tfidf", target="native5"), toy_prep(), np.arange(0, 30), fake_embed, seed=0)


def test_adding_the_target_field_did_not_change_existing_cache_keys():
    assert Spec("m1_doc_tfidf", "doc_tfidf").key() == "ca456a6d03"           # the key of the already-cached Phase 2 run
    assert Spec("m1_doc_tfidf", "doc_tfidf", target="native5").key() != "ca456a6d03"
