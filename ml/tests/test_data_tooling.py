import pandas as pd
import pytest

from iris_ml import agreement, schema
from iris_ml.splits import add_split, assign_split


def frame(**over):
    base = {
        "id": ["a", "b", "c", "d"],
        "text": ["exam stress is heavy", "I feel lonely tonight", "I want to end my life", "hello there"],
        "intent": ["stress", "emotional_support", "crisis", "other"],
        "urgency": ["low", "low", "high", "low"],
        "source": ["gold"] * 4,
        "split": ["train", "val", "test", "train"],
        "is_synthetic": [False] * 4,
        "group_id": ["g1", "g2", "g3", "g4"],
    }
    base.update(over)
    return pd.DataFrame(base)


def test_a_clean_frame_validates():
    assert schema.validate(frame()) == []
    schema.assert_valid(frame())


@pytest.mark.parametrize("over,expected", [
    ({"id": ["a", "a", "c", "d"]}, "duplicate ids"),
    ({"text": ["", "x", "y", "z"]}, "empty texts"),
    ({"urgency": ["low", "low", "urgent", "low"]}, "invalid urgency"),
    ({"intent": ["stress", "feelings", "crisis", "other"]}, "invalid intent"),
    ({"split": ["train", "val", "holdout", "train"]}, "invalid split"),
    ({"is_synthetic": [False, False, True, False]}, "synthetic rows outside the train split"),
    ({"urgency": ["low", "low", "low", "low"]}, "crisis must be at least medium"),
    ({"intent": ["stress", "emotional_support", "stress", "other"]}, "urgency=high with intent other than crisis"),
])
def test_validation_catches_each_kind_of_problem(over, expected):
    problems = schema.validate(frame(**over))
    assert any(expected in p for p in problems), problems


def test_group_leakage_across_splits_is_detected():
    problems = schema.validate(frame(group_id=["g1", "g1", "g3", "g4"], split=["train", "test", "test", "train"]))
    assert any("more than one split" in p for p in problems)


def test_identical_text_in_two_splits_is_detected_even_with_different_case_and_spacing():
    problems = schema.validate(frame(text=["I feel   LONELY", "i feel lonely", "x y", "z w"],
                                     split=["train", "test", "test", "train"]))
    assert any("identical texts" in p for p in problems)


def test_missing_columns_reported():
    assert "missing required columns" in schema.validate(frame().drop(columns=["group_id"]))[0]


def test_assert_valid_raises_with_all_problems():
    with pytest.raises(ValueError, match="duplicate ids"):
        schema.assert_valid(frame(id=["a", "a", "c", "d"]))


# --- splitting --------------------------------------------------------------------------------------------------

def test_split_is_deterministic_and_seed_dependent():
    assert assign_split("user-42", 0) == assign_split("user-42", 0)
    assert any(assign_split(f"u{i}", 0) != assign_split(f"u{i}", 1) for i in range(50))


def test_split_ratios_are_roughly_respected():
    labels = [assign_split(f"u{i}") for i in range(5000)]
    share = {s: labels.count(s) / len(labels) for s in ("train", "val", "test")}
    assert share["train"] == pytest.approx(0.70, abs=0.03)
    assert share["val"] == pytest.approx(0.15, abs=0.03) and share["test"] == pytest.approx(0.15, abs=0.03)


def test_rows_of_one_group_always_share_a_split_and_synthetic_is_train_only():
    df = pd.DataFrame({"group_id": ["u1", "u1", "u1", "u2", "u3"],
                       "is_synthetic": [False, False, False, False, True]})
    out = add_split(df)
    assert out[out.group_id == "u1"]["split"].nunique() == 1
    assert out.loc[4, "split"] == "train"


def test_a_groups_split_does_not_change_when_data_is_added():
    before = assign_split("user-7", seed=3)
    add_split(pd.DataFrame({"group_id": ["user-7", "user-8", "user-9"], "is_synthetic": [False] * 3}), seed=3)
    assert assign_split("user-7", seed=3) == before


def test_bad_ratios_rejected():
    with pytest.raises(ValueError):
        assign_split("x", ratios=(0.5, 0.2, 0.2))


# --- annotator agreement ----------------------------------------------------------------------------------------

def ann(urg, intent):
    return pd.DataFrame({"id": list("abcdef"), "urgency": urg, "intent": intent})


def test_identical_annotators_agree_perfectly():
    a = ann(["low", "medium", "high", "low", "high", "medium"], ["stress", "stress", "crisis", "other", "crisis", "stress"])
    r = agreement.compare(a, a)
    assert r["urgency_kappa_quadratic"] == 1.0 and r["intent_kappa"] == 1.0 and r["meets_target"]


def test_disagreement_lowers_kappa_and_fails_the_target():
    a = ann(["low", "medium", "high", "low", "high", "medium"], ["stress", "stress", "crisis", "other", "crisis", "stress"])
    b = ann(["high", "low", "low", "medium", "medium", "high"], ["crisis", "other", "stress", "stress", "other", "crisis"])
    r = agreement.compare(a, b)
    assert r["urgency_kappa_quadratic"] < agreement.KAPPA_TARGET and not r["meets_target"]


def test_adjudication_queue_lists_disagreements_with_high_first():
    a = ann(["low", "medium", "high", "low", "low", "low"], ["stress"] * 6)
    b = ann(["low", "low", "low", "low", "medium", "low"], ["stress"] * 6)
    q = agreement.to_adjudicate(a, b)
    assert q.iloc[0]["id"] == "c" and set(q["id"]) == {"b", "c", "e"}      # the High disagreement comes first
    assert bool(q.iloc[0]["involves_high"]) is True and len(q) == 3


def test_kappa_degenerate_single_label_case():
    assert agreement.cohens_kappa(["x", "x"], ["x", "x"]) == 1.0


def test_comparing_sets_with_no_shared_ids_fails_loudly():
    with pytest.raises(ValueError):
        agreement.compare(ann(["low"] * 6, ["stress"] * 6), ann(["low"] * 6, ["stress"] * 6).assign(id=list("uvwxyz")))
