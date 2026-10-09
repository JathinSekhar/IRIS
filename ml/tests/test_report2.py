"""The report's comparison helpers decide what is called 'better', so they get their own tests."""
import numpy as np

from iris_ml import report2 as r2
from iris_ml.experiments import Result, Spec


def fake_result(p_high: np.ndarray, name="m") -> Result:
    n = len(p_high)
    cal = np.zeros((1, n, 3))
    cal[0, :, 2] = p_high
    cal[0, :, 0] = 1 - p_high
    return Result(Spec(name, "emb_lr"), "toy", cal.copy(), cal, (cal @ np.arange(3.0))[0:1].reshape(1, n), np.array([1.0]))


def test_pct_and_diff_formatting():
    assert r2.pct(0.456) == "46%" and r2.pct(float("nan")) == "n/a" and r2.pct(None) == "n/a"
    d = {"diff": 0.05, "ci_low": -0.02, "ci_high": 0.12, "distinguishable": False}
    assert "not distinguishable" in r2._fmt_diff(d) and "+0.05" in r2._fmt_diff(d)
    assert "(distinguishable)" in r2._fmt_diff({**d, "ci_low": 0.01, "distinguishable": True})


def test_paired_comparison_detects_a_better_ranker_and_a_tie():
    rng = np.random.default_rng(0)
    y = np.array([2] * 60 + [0] * 140)
    good = np.where(y == 2, rng.uniform(0.6, 1.0, 200), rng.uniform(0.0, 0.5, 200))      # ranks High cases first
    noise = rng.uniform(0, 1, 200)                                                       # random ranking
    better = r2.paired(y, fake_result(noise), fake_result(good))
    assert better["auroc"]["diff"] > 0.3 and better["auroc"]["distinguishable"] and better["recall30"]["distinguishable"]
    assert better["mcnemar"]["only_b_correct"] > better["mcnemar"]["only_a_correct"] and better["mcnemar"]["p_value"] < 0.01
    tie = r2.paired(y, fake_result(good), fake_result(good.copy()))
    assert tie["auroc"]["diff"] == 0 and not tie["auroc"]["distinguishable"] and tie["mcnemar"]["p_value"] == 1.0


def test_paired_comparison_is_antisymmetric():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 3, 150)
    a, b = fake_result(rng.random(150), "a"), fake_result(rng.random(150), "b")
    ab, ba = r2.paired(y, a, b), r2.paired(y, b, a)
    assert ab["auroc"]["diff"] == -ba["auroc"]["diff"] or abs(ab["auroc"]["diff"] + ba["auroc"]["diff"]) < 1e-9


def test_lookup_returns_stored_probabilities_by_text():
    lk = r2._Lookup(["a", "b"], np.array([[1.0, 0, 0], [0, 0, 1.0]]))
    assert np.array_equal(lk(["b", "a"]), np.array([[0, 0, 1.0], [1.0, 0, 0]]))
