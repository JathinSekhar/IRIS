"""The decision layer is safety-critical: these tests pin down what it may and may not do."""
import numpy as np
import pytest

from iris_ml import decision as d
from iris_ml import metrics as m
from iris_ml import ranking as rk
from iris_ml.decision import DecisionPolicy, decide

SURE_LOW = np.array([0.95, 0.04, 0.01])
SURE_MED = np.array([0.05, 0.90, 0.05])
SURE_HIGH = np.array([0.02, 0.08, 0.90])
UNSURE = np.array([0.40, 0.35, 0.25])
CALM = "I have a lot of coursework this week and I am feeling a bit tired"


def test_confident_low_with_nothing_else_is_ordinary_support():
    r = decide(SURE_LOW, CALM)
    assert r.urgency == "low" and r.route == "normal_support" and not r.needs_human


def test_model_alone_follows_the_cost_matrix_toward_escalation():
    # 55% Low / 45% High: the cheapest action is NOT Low, because a missed High costs ten times a false alarm
    r = decide(np.array([0.55, 0.0, 0.45]), CALM, policy=DecisionPolicy(min_confidence=0.0))
    assert r.model_urgency == "high" and r.route == "human_reviewer"


def test_uncertain_cases_go_to_a_human_not_to_low():
    r = decide(UNSURE, CALM)
    assert r.needs_human and r.route == "human_reviewer" and any("confidence" in x for x in r.reasons)


def test_high_always_reaches_the_human_reviewer():
    r = decide(SURE_HIGH, CALM)
    assert r.urgency == "high" and r.route == "human_reviewer" and r.needs_human


def test_rule_layer_overrides_a_confident_low_model():
    r = decide(SURE_LOW, "I am going to kill myself tonight")
    assert r.urgency == "high" and r.needs_human and r.model_urgency == "low"
    assert any("rule layer" in x for x in r.reasons) and any("raised above" in x for x in r.reasons)


def test_review_level_rule_cannot_leave_the_message_low():
    r = decide(SURE_LOW, "sometimes I just want to die")
    assert r.urgency == "medium" and r.route in ("counsellor", "human_reviewer")


def test_baseline_floor_cannot_be_lowered_by_a_calm_model_or_calm_text():
    assert decide(SURE_LOW, CALM, baseline_floor="medium").urgency == "medium"
    r = decide(SURE_LOW, CALM, baseline_floor="high")
    assert r.urgency == "high" and r.needs_human and r.route == "human_reviewer"
    assert any("baseline floor" in x for x in r.reasons)


def test_floor_only_ever_raises_never_lowers():
    for probs in (SURE_LOW, SURE_MED, SURE_HIGH, UNSURE):
        base = decide(probs, CALM)
        for floor in ("none", "medium", "high"):
            assert d.URGENCY.index(decide(probs, CALM, baseline_floor=floor).urgency) >= d.URGENCY.index(base.urgency)


def test_no_model_means_human_review_but_safety_layers_still_work():
    r = decide(None, CALM)
    assert r.needs_human and r.route == "human_reviewer" and r.confidence is None
    assert decide(None, "I want to kill myself tonight").urgency == "high"


def test_out_of_scope_input_goes_to_a_human():
    assert decide(SURE_LOW, "ok").needs_human                                           # too short
    assert decide(SURE_LOW, "").needs_human
    hindi = "नमस्ते मैं ठीक नहीं हूँ बहुत परेशान"
    assert decide(SURE_LOW, hindi).needs_human


# --- the V1 design: rules + floor -> model ranks -> a human reviews every case -> the human decides ---------------------------------

def test_v1_policy_never_lets_the_model_clear_a_case():
    for probs in (SURE_LOW, SURE_MED, SURE_HIGH, UNSURE, None):
        for floor in ("none", "medium", "high"):
            r = decide(probs, CALM, floor, d.V1_POLICY)
            assert r.needs_human and r.route == "human_reviewer"
            assert any("mandatory human review" in x for x in r.reasons)
    # the evaluation policy, by contrast, is allowed to (that is exactly what the Phase 2 report measures)
    assert not decide(SURE_LOW, CALM).needs_human


def test_v1_policy_still_orders_the_queue_by_risk_and_never_lowers_a_layer():
    low, med, high = (decide(p, CALM, policy=d.V1_POLICY).risk_score for p in (SURE_LOW, SURE_MED, SURE_HIGH))
    assert low < med < high
    assert decide(SURE_LOW, "I am going to kill myself tonight", policy=d.V1_POLICY).urgency == "high"
    assert decide(SURE_LOW, CALM, "high", d.V1_POLICY).urgency == "high"
    assert d.URGENCY.index(decide(SURE_HIGH, CALM, policy=d.V1_POLICY).urgency) >= d.URGENCY.index(decide(SURE_HIGH, CALM).urgency)


def test_v1_policy_only_adds_review_it_changes_nothing_else():
    for probs in (SURE_LOW, SURE_MED, SURE_HIGH, UNSURE):
        a, b = decide(probs, CALM), decide(probs, CALM, policy=d.V1_POLICY)
        assert (a.urgency, a.model_urgency, a.confidence, a.risk_score) == (b.urgency, b.model_urgency, b.confidence, b.risk_score)
        assert b.needs_human and (a.needs_human is False or a.route == b.route)


def test_bad_floor_value_is_rejected():
    with pytest.raises(ValueError):
        decide(SURE_LOW, CALM, baseline_floor="urgent")


def test_risk_score_orders_a_maybe_high_above_a_sure_medium():
    assert d.risk_score(np.array([[0.1, 0.5, 0.4]]))[0] > d.risk_score(SURE_MED[None, :])[0]
    assert d.risk_score(SURE_HIGH[None, :])[0] > d.risk_score(SURE_LOW[None, :])[0]


def test_triage_result_carries_an_audit_trail_and_valid_probabilities():
    r = decide(SURE_MED, "my friend says he wants to kill himself")
    assert r.reasons and r.rule_level != "none" and r.probabilities is not None
    assert sum(r.probabilities) == pytest.approx(1.0)


def test_simulation_reports_missed_high_cases_that_nobody_reads():
    y = np.array([2, 2, 0, 1])
    probs = np.array([SURE_LOW, SURE_HIGH, SURE_LOW, SURE_MED])               # first High case is confidently missed
    s = d.simulate(y, probs, [CALM] * 4)
    assert s["high_total"] == 2 and s["high_auto_missed"] == 1 and s["high_caught"] == 1
    assert 0 <= s["human_review_rate"] <= 1


def test_a_stricter_policy_never_misses_more_high_cases():
    rng = np.random.default_rng(0)
    probs = rng.dirichlet([1, 1, 1], size=200)
    y = rng.integers(0, 3, size=200)
    texts = [CALM] * 200
    loose = d.simulate(y, probs, texts, DecisionPolicy(min_confidence=0.4))
    strict = d.simulate(y, probs, texts, DecisionPolicy(min_confidence=0.8))
    assert strict["high_auto_missed"] <= loose["high_auto_missed"] and strict["human_review_rate"] >= loose["human_review_rate"]


# --- ranking metrics ------------------------------------------------------------------------------------------------

def test_recall_at_review_rate_hand_check_and_monotone():
    y = [2, 0, 2, 1, 0, 0, 2, 0, 0, 0]
    score = [0.9, 0.1, 0.8, 0.5, 0.2, 0.3, 0.4, 0.05, 0.15, 0.0]
    t = rk.recall_at_review_rate(y, score, [0.1, 0.2, 0.3, 0.5, 1.0]).set_index("review_rate")
    assert t.loc[0.1, "high_seen"] == 1 and t.loc[0.2, "high_seen"] == 2 and t.loc[1.0, "recall"] == 1.0
    assert t["recall"].is_monotonic_increasing


def test_random_scores_find_about_the_review_rate():
    rng = np.random.default_rng(3)
    y = rng.integers(0, 3, 4000)
    t = rk.recall_at_review_rate(y, rng.random(4000), [0.3])
    assert t.loc[0, "recall"] == pytest.approx(0.3, abs=0.04)


def test_auroc_and_pr_auc_extremes():
    y = [0, 0, 1, 2, 2]
    assert rk.auroc_high(y, [0.0, 0.1, 0.2, 0.9, 0.95]) == 1.0
    assert rk.auroc_high(y, [0.9, 0.8, 0.5, 0.1, 0.0]) == 0.0
    assert rk.pr_auc_high(y, [0.0, 0.1, 0.2, 0.9, 0.95]) == 1.0
    assert np.isnan(rk.auroc_high([0, 1, 0], [0.1, 0.2, 0.3]))                 # no High cases: undefined, not 1.0


def test_paired_bootstrap_detects_a_clear_difference_and_not_a_tie():
    rng = np.random.default_rng(1)
    y = np.array([2] * 60 + [0] * 140)
    good = np.where(rng.random(200) < 0.9, y, 0)
    bad = np.where(rng.random(200) < 0.4, y, 0)
    rec = lambda t, p: m.recall_with_ci(t, p)["recall"]
    clear = rk.paired_bootstrap_diff(rec, y, bad, good, n_boot=400, seed=2)
    assert clear["diff"] > 0.3 and clear["distinguishable"]
    tie = rk.paired_bootstrap_diff(rec, y, good, good.copy(), n_boot=400, seed=2)
    assert tie["diff"] == 0 and not tie["distinguishable"]


def test_mcnemar_only_uses_disagreements():
    a = [True] * 10 + [False] * 10
    r = rk.mcnemar_exact(a, a)
    assert r["p_value"] == 1.0 and r["only_a_correct"] == r["only_b_correct"] == 0
    r2 = rk.mcnemar_exact([True] * 20 + [False] * 5, [False] * 20 + [False] * 5)
    assert r2["only_a_correct"] == 20 and r2["p_value"] < 0.001


# --- explicit first-person statements about ending one's life are urgent under the V1 policy ---------------------------------------------------------------

@pytest.mark.parametrize("text", ["I have been thinking about ending my life", "I want to kill myself", "I want to die", "I keep thinking about ending my own life"])
def test_v1_treats_explicit_ideation_as_urgent_whatever_the_model_says(text):
    for probs in (SURE_LOW, SURE_MED, SURE_HIGH, UNSURE, None):
        r = decide(probs, text, policy=d.V1_POLICY)
        assert r.urgency == "high" and r.needs_human and r.route == "human_reviewer" and r.risk_score >= 2.0
        assert any("ending their own life" in x for x in r.reasons)


@pytest.mark.parametrize("text", ["My friend said he wants to kill himself", "I'm not suicidal, just stressed", "I don't want to die, I just want the pain to stop",
                                  "Nobody would notice if I was gone", "I've been cutting myself"])
def test_v1_keeps_negated_third_person_and_indirect_statements_at_review_level_not_urgent(text):
    r = decide(SURE_LOW, text, policy=d.V1_POLICY)
    assert r.urgency == "medium" and r.needs_human, text


def test_the_evaluation_policy_is_unchanged_so_reported_results_still_hold():
    assert decide(SURE_LOW, "I want to kill myself").urgency == "medium"
    assert not DecisionPolicy().urgent_ideation and not DecisionPolicy().mandatory_review
