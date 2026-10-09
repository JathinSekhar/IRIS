"""Tests for chunking, near-duplicate detection, the synthetic generator and the challenge set."""
import numpy as np
import pandas as pd
import pytest

from iris_ml import challenge, chunks, schema, synth
from iris_ml.rules import scan


def docs():
    long = " ".join(f"This is sentence number {i} in a rather long personal story about my week and how it went at home." for i in range(60))
    return pd.DataFrame({"id": ["a", "b", "c"], "text": [long, "A short but complete message about how I feel today at school and home, honestly.", "tiny"],
                         "native_label": ["Ideation", "Supportive", "Indicator"], "urgency": ["medium", "low", "medium"]})


# --- chunks -----------------------------------------------------------------------------------------------------

def test_chunks_inherit_labels_cap_long_documents_and_keep_order():
    ch = chunks.build_chunks(docs(), max_chunks_per_doc=8)
    assert set(ch.doc_id) == {"a", "b", "c"} and ch.chunk_id.is_unique
    a = ch[ch.doc_id == "a"]
    assert len(a) == 8 and a.position.is_monotonic_increasing and set(a.urgency) == {"medium"}
    assert (ch.text.str.len() <= 600).all()
    assert len(ch[ch.doc_id == "c"]) == 1                      # a tiny document is kept whole, never dropped


# --- near duplicates --------------------------------------------------------------------------------------------

def test_near_duplicates_are_found_even_when_edited_and_unrelated_text_is_not():
    base = " ".join(f"word{i} filler{i % 7} thing{i % 11}" for i in range(80))
    edited = base.replace("word10", "changed").replace("word30", "other")
    unrelated = " ".join(f"alpha{i} beta{i % 5} gamma{i % 13}" for i in range(80))
    pairs = chunks.near_duplicate_pairs([base, edited, unrelated], threshold=0.5)
    assert [(i, j) for i, j, _ in pairs] == [(0, 1)]
    groups = chunks.duplicate_groups(3, pairs)
    assert groups[0] == groups[1] != groups[2]


def test_pooling_methods():
    vals = np.array([[0.1], [0.9], [0.5], [0.3]])
    idx = np.array([0, 0, 1, 1])
    assert np.allclose(chunks.pool_scores(vals, idx, 2, "mean").ravel(), [0.5, 0.4])
    assert np.allclose(chunks.pool_scores(vals, idx, 2, "max").ravel(), [0.9, 0.5])
    assert np.allclose(chunks.pool_scores(vals, idx, 2, "topk", k=1).ravel(), [0.9, 0.5])
    with pytest.raises(ValueError):
        chunks.pool_scores(vals, idx, 2, "median")


# --- synthetic data ---------------------------------------------------------------------------------------------

def test_synthetic_data_is_flagged_train_only_valid_and_deterministic():
    s = synth.build_synthetic(n_rounds=60, seed=1)
    assert s.is_synthetic.all() and set(s.split) == {"train"} and set(s.source) == {synth.SOURCE}
    schema.assert_valid(s)
    assert s.equals(synth.build_synthetic(n_rounds=60, seed=1))
    assert not s.equals(synth.build_synthetic(n_rounds=60, seed=2))
    assert s.id.is_unique and s.text.is_unique


def test_synthetic_covers_every_class_and_follows_the_guide():
    s = synth.build_synthetic(n_rounds=120, seed=0)
    assert set(s.urgency) == {"low", "medium", "high"} and set(s.intent) == {"stress", "emotional_support", "other", "crisis"}
    assert (s[s.urgency == "high"].intent == "crisis").all() and not ((s.intent == "crisis") & (s.urgency == "low")).any()
    assert (s.urgency == "low").mean() > 0.5                    # mostly ordinary chat, which is the point


def test_synthetic_contains_no_method_details():
    s = synth.build_synthetic(n_rounds=200, seed=0)
    import re
    forbidden = re.compile(r"(rope|gun|bridge|overdose|razor|poison|noose|jump(ed|ing)?|hang(ed|ing)? (myself|himself|herself))")
    assert not [t for t in s.text.str.lower() if forbidden.search(t)]


# --- challenge set ----------------------------------------------------------------------------------------------

def test_challenge_set_is_well_formed_and_balanced_enough_to_be_useful():
    c = challenge.challenge_frame()
    assert c.id.is_unique and c.text.is_unique and len(c) >= 70
    assert set(c.expect) == {"low", "medium_plus", "high"}
    assert (c.expect == "low").sum() >= 25 and (c.expect == "high").sum() >= 10


def test_challenge_set_shares_no_wording_with_the_training_templates():
    frags = synth.template_fragments()
    c = challenge.challenge_frame()
    overlap = [t for t in c.text if t.lower().strip(" .!?") in frags]
    assert overlap == []
    synthetic = set(synth.build_synthetic(n_rounds=300, seed=2026).text.str.lower().str.strip(" .!?"))
    assert not [t for t in c.text if t.lower().strip(" .!?") in synthetic]


def test_rule_layer_never_escalates_the_benign_challenge_items():
    c = challenge.challenge_frame()
    flagged = [t for t, e in zip(c.text, c.expect) if e == "low" and scan(t).flagged]
    assert flagged == []


def test_rule_layer_alone_reports_what_it_misses_on_the_hard_items():
    c = challenge.challenge_frame()
    hard = c[c.category == "implicit_high"]
    assert len(hard) >= 3 and sum(scan(t).level == "high" for t in hard.text) < len(hard)   # documents the known gap


def test_evaluate_challenge_scores_a_perfect_and_an_alarmist_system():
    c = challenge.challenge_frame()
    texts = list(c.text)
    perfect_urg = ["low" if e == "low" else ("medium" if e == "medium_plus" else "high") for e in c.expect]
    perfect = challenge.evaluate_challenge(texts, perfect_urg, [e == "high" for e in c.expect])
    assert perfect["overall"]["passed"] == perfect["overall"]["total"] and perfect["failures"] == []
    alarmist = challenge.evaluate_challenge(texts, ["high"] * len(c), [True] * len(c))
    assert alarmist["benign_stay_low"]["passed"] == 0 and alarmist["must_escalate_met"]["passed"] == alarmist["must_escalate_met"]["total"]
    with pytest.raises(ValueError):
        challenge.evaluate_challenge(texts[::-1], perfect_urg, [False] * len(c))
