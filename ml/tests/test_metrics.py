"""Metric tests use small cases whose answers can be worked out by hand."""
import math

import numpy as np
import pandas as pd
import pytest

from iris_ml import metrics as m


def test_wilson_interval_matches_hand_calculation():
    lo, hi = m.wilson_interval(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-3) and hi == pytest.approx(0.9433, abs=1e-3)
    assert m.wilson_interval(0, 10)[0] == 0.0
    assert m.wilson_interval(10, 10)[1] == 1.0
    assert m.wilson_interval(0, 0) == (0.0, 1.0)           # no data means no information, not "perfect"


def test_interval_narrows_with_more_data():
    w_small = np.subtract(*m.wilson_interval(19, 20)[::-1])
    w_big = np.subtract(*m.wilson_interval(190, 200)[::-1])
    assert w_big < w_small


def test_high_recall_counts_only_true_high_cases():
    r = m.recall_with_ci([2, 2, 2, 1, 0], [2, 1, 2, 2, 0])
    assert (r["caught"], r["total"]) == (2, 3) and r["recall"] == pytest.approx(2 / 3)
    assert 0 <= r["ci_low"] < r["recall"] < r["ci_high"] <= 1


def test_high_recall_with_no_high_cases_is_nan_not_one():
    r = m.recall_with_ci([0, 1, 0], [0, 1, 0])
    assert math.isnan(r["recall"]) and r["total"] == 0


def test_perfect_predictions_give_perfect_scores():
    y = [0, 1, 2, 0, 1, 2, 2, 0]
    rep = m.urgency_report(y, y)
    assert rep["macro_f1"] == 1.0 and rep["quadratic_weighted_kappa"] == 1.0
    assert rep["high_recall"]["recall"] == 1.0
    assert rep["confusion_matrix"] == [[3, 0, 0], [0, 2, 0], [0, 0, 3]]


def test_quadratic_kappa_penalises_far_errors_more_than_near_ones():
    y = [0, 0, 1, 1, 2, 2, 0, 1, 2, 1]
    near = [0, 0, 1, 1, 1, 1, 0, 1, 1, 1]   # High mistaken for Medium (one step)
    far = [0, 0, 1, 1, 0, 0, 0, 1, 0, 1]    # High mistaken for Low (two steps)
    assert m.urgency_report(y, near)["quadratic_weighted_kappa"] > m.urgency_report(y, far)["quadratic_weighted_kappa"]


def test_confusion_matrix_rows_are_true_columns_are_predicted():
    rep = m.urgency_report([2, 2, 0], [0, 2, 0])
    assert rep["confusion_matrix"][2] == [1, 0, 1]          # true High: one predicted Low, one predicted High


def test_ece_zero_for_calibrated_and_large_for_overconfident():
    probs = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], [1.0, 0, 0]])
    assert m.ece(probs, [0, 1, 2, 0]) == pytest.approx(0.0)
    assert m.ece(probs, [0, 1, 2, 1]) == pytest.approx(0.25)             # 100% sure, right 3 of 4 times
    over = np.tile([1.0, 0, 0], (10, 1))
    assert m.ece(over, [0] * 5 + [1] * 5) == pytest.approx(0.5)          # 100% sure, right half the time


def test_ece_matches_a_hand_computed_value():
    probs = np.array([[0.6, 0.4, 0.0]] * 5)
    y = [0, 0, 0, 1, 1]                                                  # confidence 0.6, accuracy 0.6
    assert m.ece(probs, y) == pytest.approx(0.0)
    assert m.ece(probs, [0, 1, 1, 1, 1]) == pytest.approx(0.4)           # accuracy 0.2 vs confidence 0.6


def test_cost_matrix_encodes_miss_high_worse_than_false_alarm():
    matrix, review_cost = m.load_costs()
    assert matrix.shape == (3, 3) and review_cost > 0
    assert np.all(np.diag(matrix) == 0)
    miss_high, false_alarm = matrix[2, 0], matrix[0, 2]
    assert miss_high >= 5 * false_alarm                                  # the core safety principle
    assert matrix[2, 0] > matrix[2, 1] > matrix[2, 2]                    # the further below, the worse


def test_expected_cost_hand_check():
    matrix, _ = m.load_costs()
    assert m.expected_cost([2, 0], [0, 2], matrix) == pytest.approx((matrix[2, 0] + matrix[0, 2]) / 2)
    assert m.expected_cost([0, 1, 2], [0, 1, 2], matrix) == 0.0


def test_review_curve_extremes():
    y = [2, 1, 0, 2]
    probs = np.array([[0.1, 0.1, 0.8], [0.2, 0.6, 0.2], [0.7, 0.2, 0.1], [0.6, 0.3, 0.1]])  # last High is mispredicted
    curve = m.review_curve(y, probs, thresholds=[0.0, 1.01])
    none, everyone = curve.iloc[0], curve.iloc[1]
    assert none["review_rate"] == 0.0 and none["high_recall"] == pytest.approx(0.5)      # the second High is missed
    assert everyone["review_rate"] == 1.0 and everyone["high_recall"] == 1.0
    assert everyone["mean_cost"] == pytest.approx(m.load_costs()[1])                      # flat review cost for all


def test_review_curve_more_review_never_hurts_recall():
    rng = np.random.default_rng(0)
    probs = rng.dirichlet([1, 1, 1], size=300)
    y = rng.integers(0, 3, size=300)
    curve = m.review_curve(y, probs, thresholds=np.linspace(0.3, 1.0, 15))
    assert curve["review_rate"].is_monotonic_increasing
    assert curve["high_recall"].is_monotonic_increasing


def test_cheapest_review_for_recall_picks_lowest_review_rate_meeting_target():
    curve = pd.DataFrame({"threshold": [0.4, 0.6, 0.8], "review_rate": [0.05, 0.2, 0.5],
                          "high_recall": [0.80, 0.96, 1.0], "mean_cost": [2.0, 1.2, 1.0]})
    assert m.cheapest_review_for_recall(curve, 0.95)["threshold"] == 0.6
    assert m.cheapest_review_for_recall(curve, 1.01) is None


def test_bootstrap_interval_contains_the_point_estimate():
    y = np.array([2] * 40 + [0] * 60)
    pred = np.array([2] * 36 + [0] * 4 + [0] * 60)
    point = m.recall_with_ci(y, pred)["recall"]
    lo, hi = m.bootstrap_ci(lambda t, p: m.recall_with_ci(t, p)["recall"], y, pred, n_boot=500, seed=1)
    assert lo <= point <= hi and hi - lo > 0


def test_slice_report_flags_the_weak_slice():
    df = pd.DataFrame({"y_true": [2, 2, 2, 2, 2, 2, 0], "y_pred": [2, 2, 2, 0, 0, 2, 0],
                       "lang": ["en", "en", "en", "hi", "hi", "hi", "en"]})
    out = m.slice_high_recall(df, "lang").set_index("lang")
    assert out.loc["en", "recall"] == 1.0 and out.loc["hi", "recall"] == pytest.approx(1 / 3)
    assert out.loc["hi", "n_high"] == 3
