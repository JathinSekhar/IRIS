import json

import numpy as np
import pytest

from iris_ml import challenge as ch
from iris_ml import system as sy
from iris_ml.decision import DecisionPolicy
from iris_ml.experiments import Spec, fit_split
from iris_ml.system import TriageSystem, fit_final
from test_experiments import fake_embed, toy_prep


def constant_system(probs, temperature=1.0):
    p = np.array(probs, dtype=float)
    return TriageSystem("const", lambda texts: np.tile(p, (len(texts), 1)), temperature)


CALM = "I have a lot of coursework this week and I am feeling a bit tired"


def test_system_applies_every_safety_layer_to_a_single_message():
    s = constant_system([0.95, 0.04, 0.01])
    assert s.triage(CALM).urgency == "low"
    assert s.triage("I am going to kill myself tonight").urgency == "high"                  # rules beat a confident model
    assert s.triage(CALM, baseline_floor="high").urgency == "high"                           # check-in floor beats it too


def test_temperature_softens_confidence():
    sharp = constant_system([0.98, 0.01, 0.01], temperature=1.0).probabilities([CALM])[0]
    soft = constant_system([0.98, 0.01, 0.01], temperature=3.0).probabilities([CALM])[0]
    assert soft.max() < sharp.max() and soft.sum() == pytest.approx(1.0)


def test_fit_final_scores_messages_for_every_family_that_supports_it():
    prep = toy_prep()
    for fam, kw in [("doc_tfidf", {}), ("chunk_tfidf", {}), ("emb_lr", {"embedder": "fake"}), ("mil", {"embedder": "fake", "epochs": 120})]:
        s = fit_final(Spec("t", fam, repeats=1, **kw), prep, fake_embed, temperature=1.0)
        p = s.probabilities(["calm study tea walk friend today", "tonight goodbye pills ending final"])
        assert p.shape == (2, 3) and np.allclose(p.sum(axis=1), 1.0, atol=1e-5), fam
        assert p[0].argmax() < p[1].argmax(), fam                                               # low text scores lower than high text


def test_fit_final_never_uses_users_outside_the_prepared_development_set():
    prep = toy_prep()
    fitted = fit_split(Spec("t", "chunk_tfidf", repeats=1), prep, np.arange(len(prep.y)), fake_embed, seed=0)
    assert fitted.predict_texts is not None and len(prep.dev) == len(prep.y)


def test_workload_counts_humans_and_rule_flags():
    s = constant_system([0.40, 0.35, 0.25])                                                      # always unsure
    w = sy.workload(s, [CALM, "sometimes I want to die", "hello there friend how are you"], min_confidences=(0.5, 0.3))
    assert w["by_min_confidence"]["0.50"]["needs_human"] == 1.0                                  # unsure everywhere -> all to humans
    assert w["rule_flag_rate"] == pytest.approx(1 / 3)
    # at 0.30 confidence the model is never "unsure", yet the cost matrix still escalates a 40/35/25 case to High
    assert w["by_min_confidence"]["0.30"]["final_high"] == 1.0
    s2 = constant_system([0.97, 0.02, 0.01])
    w2 = sy.workload(s2, [CALM, "thanks that helped me a lot today"], min_confidences=(0.6,))
    assert w2["by_min_confidence"]["0.60"]["needs_human"] == 0.0 and w2["by_min_confidence"]["0.60"]["final_low"] == 1.0


def test_esconv_messages_are_filtered_sampled_and_deterministic(tmp_path):
    convo = [{"dialog": [{"speaker": "seeker", "content": "I feel really stressed about work lately"},
                         {"speaker": "supporter", "content": "I am sorry to hear that, tell me more"},
                         {"speaker": "seeker", "content": "ok"},
                         {"speaker": "seeker", "content": "My boss keeps piling on tasks and I cannot cope with it"}]}] * 5
    p = tmp_path / "esconv.json"
    p.write_text(json.dumps(convo), encoding="utf-8")
    a = sy.esconv_messages(n=3, seed=1, path=p)
    assert len(a) == 3 and a == sy.esconv_messages(n=3, seed=1, path=p)
    assert all(len(m.split()) >= 3 for m in a) and not any("sorry" in m for m in a)               # no supporter text, no tiny turns


def test_challenge_runs_for_rules_alone_and_for_a_system():
    rules_only = sy.challenge(None)
    assert rules_only["benign_stay_low"]["passed"] == rules_only["benign_stay_low"]["total"]
    assert rules_only["by_category"]["implicit_high"]["passed"] < rules_only["by_category"]["implicit_high"]["total"]
    alarmist = sy.challenge(constant_system([0.0, 0.0, 1.0]))
    assert alarmist["benign_stay_low"]["passed"] == 0 and alarmist["must_escalate_met"]["passed"] == alarmist["must_escalate_met"]["total"]
    calm = sy.challenge(constant_system([1.0, 0.0, 0.0]))
    assert calm["benign_stay_low"]["passed"] == calm["benign_stay_low"]["total"]                  # model silent, rules still escalate
    assert calm["must_escalate_met"]["passed"] >= rules_only["must_escalate_met"]["passed"]
    assert len(ch.challenge_frame()) == rules_only["overall"]["total"]


# --- fail-safe invariant from docs/TRIAGE_INTEGRATION_SPEC.md ------------------------------------------------------------------

def broken_system(exc=None, bad=None):
    def predict(texts):
        if exc:
            raise exc
        return bad
    return TriageSystem("broken", predict)


@pytest.mark.parametrize("make", [
    lambda: broken_system(exc=RuntimeError("GPU out of memory")),
    lambda: broken_system(bad=np.full((1, 3), np.nan)),
    lambda: broken_system(bad=np.ones((1, 5)) / 5),
])
def test_a_broken_model_never_turns_into_low(make):
    s = make()
    r = s.triage(CALM)
    assert r.needs_human and r.route == "human_reviewer" and r.confidence is None
    assert any("no model" in x for x in r.reasons)
    assert s.triage("I am going to kill myself tonight").urgency == "high"          # rules still work with a dead model
    assert s.triage(CALM, baseline_floor="high").urgency == "high"                  # and so does the check-in floor



# --- persistence -----------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("fam,kw", [("doc_tfidf", {}), ("chunk_tfidf", {}), ("emb_lr", {"embedder": "fake"}),
                                    ("mil", {"embedder": "fake", "epochs": 100, "head": "ordinal"})])
def test_saved_systems_reload_and_give_identical_decisions(fam, kw, tmp_path):
    prep = toy_prep()
    original = fit_final(Spec("t", fam, repeats=1, **kw), prep, fake_embed, temperature=1.7)
    sy.save_system(original, tmp_path, extra={"data": "toy"})
    loaded = sy.load_system(tmp_path, embed_fn=fake_embed)
    texts = ["calm study tea walk friend today", "sad alone heavy cry tired just", "tonight goodbye pills ending final", CALM]
    assert np.allclose(original.probabilities(texts), loaded.probabilities(texts), atol=1e-5)
    assert [r.urgency for r in original.triage_batch(texts)] == [r.urgency for r in loaded.triage_batch(texts)]
    assert loaded.temperature == pytest.approx(1.7) and loaded.spec == original.spec
    assert not any(x in (tmp_path / "system.json").read_text(encoding="utf-8") for x in ["calm study", "tonight goodbye"])


def test_a_system_without_an_artifact_cannot_be_saved(tmp_path):
    with pytest.raises(ValueError, match="persistable"):
        sy.save_system(constant_system([1, 0, 0]), tmp_path)


# --- prior shift ------------------------------------------------------------------------------------------------------------------

def test_prior_shift_is_identity_for_the_same_prior_and_lowers_high_for_a_rarer_target():
    from iris_ml.calibration import adjust_prior, prior_with_high
    src = np.array([0.22, 0.54, 0.24])
    p = np.array([[0.3, 0.4, 0.3], [0.7, 0.2, 0.1], [0.1, 0.3, 0.6]])
    assert np.allclose(adjust_prior(p, src, src), p)
    tgt = prior_with_high(src, 0.02)
    assert tgt.sum() == pytest.approx(1.0) and tgt[2] == pytest.approx(0.02) and tgt[1] / tgt[0] == pytest.approx(src[1] / src[0])
    q = adjust_prior(p, src, tgt)
    assert np.allclose(q.sum(axis=1), 1.0) and (q[:, 2] < p[:, 2]).all()
    assert (q.argmax(axis=1) <= p.argmax(axis=1)).all()                       # it can only lower, never raise, the verdict


def test_a_lower_assumed_high_rate_means_fewer_escalations_and_the_default_is_no_shift():
    src = np.array([0.22, 0.54, 0.24])
    base = constant_system([0.72, 0.09, 0.19])
    assert base.prior is None
    n0 = sy.workload(base, [CALM] * 10, min_confidences=(0.6,))["by_min_confidence"]["0.60"]["final_high"]
    rarer = sy.with_prior(base, src, 0.02)
    n1 = sy.workload(rarer, [CALM] * 10, min_confidences=(0.6,))["by_min_confidence"]["0.60"]["final_high"]
    assert n0 == 1.0 and n1 == 0.0                                           # the same message stops being escalated
    assert sy.with_prior(rarer, src, None).prior is None                      # and None switches it back off
    assert rarer.triage("I am going to kill myself tonight").urgency == "high"   # rules ignore the assumption entirely



# --- ensembles ---------------------------------------------------------------------------------------------------------------------

def test_ensemble_is_the_mean_of_calibrated_member_probabilities():
    a = constant_system([0.8, 0.1, 0.1])
    b = constant_system([0.2, 0.3, 0.5], temperature=1.0)
    e = sy.ensemble_system("e", [a, b])
    assert np.allclose(e.probabilities(["x"])[0], [0.5, 0.2, 0.3])
    assert e.triage("I am going to kill myself tonight").urgency == "high"           # safety layers apply to ensembles too
    with pytest.raises(ValueError):
        sy.ensemble_system("empty", [])


def test_each_member_keeps_its_own_temperature_inside_an_ensemble():
    sharp = constant_system([0.9, 0.05, 0.05], temperature=1.0)
    soft = constant_system([0.9, 0.05, 0.05], temperature=4.0)
    e = sy.ensemble_system("e", [sharp, soft])
    assert soft.probabilities(["x"])[0].max() < e.probabilities(["x"])[0].max() < sharp.probabilities(["x"])[0].max()


def test_a_saved_ensemble_reloads_with_identical_decisions(tmp_path):
    prep = toy_prep()
    members = [fit_final(Spec("a", "emb_lr", repeats=1, embedder="fake"), prep, fake_embed, 1.3),
               fit_final(Spec("b", "chunk_tfidf", repeats=1), prep, fake_embed, 0.8)]
    original = sy.ensemble_system("ens", members, DecisionPolicy(min_confidence=0.55))
    sy.save_system(original, tmp_path)
    loaded = sy.load_system(tmp_path, embed_fn=fake_embed)
    texts = ["calm study tea walk friend today", "tonight goodbye pills ending final", CALM]
    assert np.allclose(original.probabilities(texts), loaded.probabilities(texts), atol=1e-5)
    assert loaded.policy.min_confidence == pytest.approx(0.55)
    assert [r.urgency for r in original.triage_batch(texts)] == [r.urgency for r in loaded.triage_batch(texts)]


def test_ensemble_result_averages_out_of_fold_probabilities():
    from iris_ml.experiments import Result, ensemble_result
    def res(p):
        cal = np.tile(np.array(p, dtype=float), (1, 4, 1))
        return Result(Spec("m", "emb_lr"), "toy", cal.copy(), cal, (cal @ np.arange(3.0)), np.ones(1))
    e = ensemble_result("ens", [res([0.8, 0.1, 0.1]), res([0.2, 0.3, 0.5])])
    assert np.allclose(e.cal[0, 0], [0.5, 0.2, 0.3]) and e.spec.family == "ensemble" and np.allclose(e.cal.sum(axis=2), 1.0)
