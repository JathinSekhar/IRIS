import pytest

from app.services.questionnaire import clean_answers
from app.services.scoring import gad7_band, phq9_band, score

PHQ = ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "s0"]
GAD = ["g1", "g2", "g3", "g4", "g5", "g6", "g7"]


def fill(items, v):
    return {i: v for i in items}


@pytest.mark.parametrize(
    "s,band",
    [(0, "minimal"), (4, "minimal"), (5, "mild"), (9, "mild"), (10, "moderate"), (14, "moderate"),
     (15, "moderately_severe"), (19, "moderately_severe"), (20, "severe"), (27, "severe")],
)
def test_phq9_bands(s, band):
    assert phq9_band(s) == band


@pytest.mark.parametrize("s,band", [(4, "minimal"), (5, "mild"), (10, "moderate"), (14, "moderate"), (15, "severe")])
def test_gad7_bands(s, band):
    assert gad7_band(s) == band


def test_empty_is_unknown_not_low():
    r = score({})
    assert r["baseline_risk"] == "unknown"
    assert r["phq9"]["complete"] is False


def test_all_zero_is_low_and_complete():
    r = score({**fill(PHQ, 0), **fill(GAD, 0), "f1": 0})
    assert r["baseline_risk"] == "low"
    assert r["phq9"]["complete"] and r["gad7"]["complete"]
    assert r["safety"]["flag"] is False


def test_phq9_total_includes_item_9():
    r = score({**fill(PHQ, 1)})
    assert r["phq9"]["score"] == 9 and r["phq9"]["max"] == 27


def test_moderate_depression_is_medium_risk():
    r = score({**fill(PHQ[:8], 1), "m1": 2, "m2": 2, "s0": 0})
    assert r["phq9"]["score"] == 10
    assert r["baseline_risk"] == "medium"


def test_severe_depression_is_high_risk():
    r = score({**fill(PHQ[:8], 3)})
    assert r["phq9"]["score"] == 24
    assert r["baseline_risk"] == "high"


def test_functional_impairment_raises_to_medium():
    assert score({**fill(PHQ, 0), "f1": 2})["baseline_risk"] == "medium"


def test_s0_positive_flags_safety_tier_low():
    r = score({**fill(PHQ[:8], 0), "s0": 1, "c1": 0, "c2": 0, "c6": 0})
    assert r["safety"] == {"flag": True, "tier": 1, "tier_label": "low", "escalate": False}
    assert r["baseline_risk"] == "medium"


def test_method_without_intent_is_moderate_and_escalates():
    r = score({"s0": 2, "c1": 1, "c2": 1, "c3": 1, "c4": 0, "c5": 0, "c6": 0})
    assert r["safety"]["tier"] == 2 and r["safety"]["escalate"] is True
    assert r["baseline_risk"] == "high"


@pytest.mark.parametrize(
    "extra",
    [{"c4": 1}, {"c5": 1}, {"c6": 1, "c7": 1}],
)
def test_intent_plan_or_recent_behaviour_is_high(extra):
    base = {"s0": 3, "c1": 1, "c2": 1, "c3": 0, "c4": 0, "c5": 0, "c6": 0, **extra}
    r = score(base)
    assert r["safety"]["tier"] == 3 and r["baseline_risk"] == "high"


def test_old_behaviour_only_is_moderate():
    r = score({"s0": 1, "c6": 1, "c7": 0})
    assert r["safety"]["tier"] == 2


def test_safety_can_never_be_lowered_by_good_scores():
    answers = {**fill(PHQ[:8], 0), **fill(GAD, 0), "f1": 0, "s0": 3, "c1": 1, "c2": 1, "c4": 1}
    assert score(answers)["baseline_risk"] == "high"


# --- validation / branching -------------------------------------------------

def test_clean_answers_rejects_unknown_question():
    with pytest.raises(ValueError):
        clean_answers({"zzz": 1})


def test_clean_answers_rejects_out_of_range():
    with pytest.raises(ValueError):
        clean_answers({"m1": 9})


def test_clean_answers_rejects_bool():
    with pytest.raises(ValueError):
        clean_answers({"m1": True})


def test_clean_answers_drops_hidden_branch_answers():
    # s0 == 0 hides c1..c7, so a stray c4 must not influence scoring.
    out = clean_answers({"s0": 0, "c4": 1})
    assert "c4" not in out and out["s0"] == 0


def test_clean_answers_keeps_active_branch():
    out = clean_answers({"s0": 2, "c2": 1, "c4": 1})
    assert out["c4"] == 1


def test_clean_answers_drops_blank_text():
    assert "a1" not in clean_answers({"a1": "   "})


def test_clean_answers_limits_text_length():
    with pytest.raises(ValueError):
        clean_answers({"a1": "x" * 2001})
