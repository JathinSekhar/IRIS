"""Low-risk handling: Low means lower estimated urgency, not zero risk. These tests pin down what IRIS may and may not say or do."""
import re

import numpy as np
import pytest

from iris_ml import support as sp
from iris_ml.decision import V1_POLICY, decide

SURE_LOW = np.array([0.95, 0.04, 0.01])
SURE_MED = np.array([0.05, 0.90, 0.05])
SURE_HIGH = np.array([0.02, 0.08, 0.90])
UNSURE = np.array([0.40, 0.35, 0.25])
CALM = "I have a lot of coursework this week and I am feeling a bit tired"


def low(text=CALM, probs=SURE_LOW, floor="none"):
    return decide(probs, text, floor, V1_POLICY)


def plan(text=CALM, probs=SURE_LOW, floor="none"):
    return sp.plan_support(text, low(text, probs, floor))


# --- 1. a Low prediction is never cleared -------------------------------------------------------------------------------------------

def test_a_confident_low_prediction_is_never_cleared():
    r = low()
    assert r.urgency == "low" and r.needs_human and r.route == "human_reviewer"
    p = sp.plan_support(CALM, r)
    assert p.human_review_required and p.queue_status == "pending_human_review" and p.provisional_priority == "low"
    assert "NOT ZERO RISK" in p.reviewer_note and "not cleared" in p.reviewer_note
    assert p.a_person_may_reach_out


# --- 2. every message stays eligible for human review --------------------------------------------------------------------------------

TEXTS = [CALM, "How do I book a counsellor appointment?", "I'm so lonely here", "ok", "", "नमस्ते मैं ठीक नहीं हूँ बहुत परेशान", "hello " * 400,
         "I wish I could disappear into a good book this weekend", "my dog died last year", "I want to die", "I am going to kill myself tonight"]


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("probs", [SURE_LOW, SURE_MED, SURE_HIGH, UNSURE, None])
@pytest.mark.parametrize("floor", ["none", "medium", "high"])
def test_every_message_is_in_the_human_review_queue(text, probs, floor):
    r = decide(probs, text, floor, V1_POLICY)
    p = sp.plan_support(text, r)
    assert r.needs_human and p.human_review_required and p.queue_status == sp.QUEUE_STATUS and p.a_person_may_reach_out


# --- 3. recommendations match the message ------------------------------------------------------------------------------------------

CONTEXT = [
    ("I have exams next week and I am struggling to study", "academic_stress", "Study planning"),
    ("I feel so lonely, I have no friends here", "loneliness", "One small social step"),
    ("I can't sleep at night and I am exhausted", "sleep", "A wind-down routine"),
    ("I am worried about money and my boss keeps piling on work", "work_money", "List and shrink"),
    ("We had a big argument and my boyfriend and I broke up", "relationships", "An unsent letter"),
    ("My grandmother passed away and I miss her", "grief", "Small routines"),
    ("I feel so anxious and overwhelmed all the time", "anxiety_worry", "Grounding"),
    ("How do I find a counsellor?", "practical_help", None),
]


@pytest.mark.parametrize("text,topic,item", CONTEXT)
def test_recommendations_follow_what_the_person_wrote(text, topic, item):
    p = plan(text)
    assert p.topics[0] == topic
    if item:
        assert item in [title for title, _ in p.self_help]


def test_different_needs_get_different_plans_and_unmatched_text_gets_general_support():
    a, b = plan("I have exams next week and I am struggling to study"), plan("I feel so lonely, I have no friends here")
    assert a.self_help != b.self_help and a.reach_out != b.reach_out and a.intro != b.intro
    g = plan("The weather turned colder this week")
    assert g.topics == ("general",) and not g.self_help and g.reach_out   # nothing recognised: no tip that may not fit
    assert plan("I wish I could disappear into a good book this weekend").topics == ("general",)
    assert "academic_stress" in plan("exams and money worries and I can't sleep").topics            # several needs: the main ones show


def test_self_help_covers_what_was_asked_for():
    kinds = " ".join(f"{t} {h}" for t, h in plan("I feel anxious and low and cannot sleep").self_help).lower()
    assert "breath" in kinds or "grounding" in kinds
    allitems = " ".join(" ".join(i for i in t.reach_out) for t in sp.TOPICS).lower()
    assert "friend" in allitems and "counsellor" in allitems and "family" in allitems
    assert {sp.JOURNAL[0], sp.ROUTINE[0], sp.BREATHING[0]} == {"Journaling", "A steady daily routine", "Slow breathing"}   # journaling, routines, breathing


# --- 4. safety rules override a Low prediction -------------------------------------------------------------------------------------

def test_explicit_self_harm_triggers_the_urgent_protocol_whatever_the_model_says():
    p = plan("I am going to kill myself tonight", SURE_LOW)
    assert p.provisional_priority == "high" and p.urgent_protocol and p.show_crisis_resources
    assert "URGENT" in p.reviewer_note and "whatever any model predicted" in p.reviewer_note
    assert p.crisis_lines == sp.CRISIS_LINES and not p.self_help                  # no stress tips instead of help


def test_a_high_check_in_floor_keeps_the_case_High_for_the_reviewer_but_does_not_alarm_a_calm_message():
    p = plan(CALM, SURE_LOW, floor="high")
    assert p.provisional_priority == "high" and p.show_crisis_resources and p.helplines == sp.HELPLINES        # the reviewer still sees High, helplines are at hand
    assert not p.urgent_protocol and p.layout == "tips" and p.crisis_lead == sp.CRISIS_LEAD_FLAGGED         # but nobody is told "we are concerned" about a calm message
    assert "check-in" in p.reviewer_note and "URGENT" not in p.reviewer_note


def test_a_review_level_rule_shows_support_lines_but_is_not_the_urgent_protocol():
    p = plan("Nobody would notice if I was gone", SURE_LOW)
    assert p.show_crisis_resources and p.provisional_priority == "medium" and not p.urgent_protocol


def test_calm_low_messages_do_not_get_a_crisis_banner():
    p = plan()
    assert not p.show_crisis_resources and p.crisis_lines == () and not p.urgent_protocol


# --- 5. no unsupported claims ------------------------------------------------------------------------------------------------------

BANNED = [
    r"\byou(?:'re| are) (?:safe|fine|okay|ok|all right|not at risk|in no danger)", r"\bno (?:risk|danger)\b", r"\bnot at risk\b", r"\bnothing to worry",
    r"\bdon'?t worry\b", r"\bdiagnos", r"\byou (?:have|suffer from|are suffering from|probably have|might have) (?:depression|anxiety|a disorder|a mental|an? \w+ disorder)",
    r"\bcure\b", r"\bguarantee", r"\bsafe\b",
    r"\b(?:risk|urgent|urgency|priority|score|low|medium|high)\b",          # no scores or labels shown to the person
]


def _all_user_facing_strings():
    texts = [user for user in (sp.user_facing_text(plan(t, p, f)) for t, _, _ in CONTEXT for p in (SURE_LOW, SURE_HIGH) for f in ("none", "high"))]
    texts += [sp.user_facing_text(plan(t)) for t in TEXTS]
    for t in sp.ALL_TOPICS:
        texts += [t.intro, *t.reach_out, *[f"{a}: {b}" for a, b in t.self_help]]
    return texts + list(sp.CRISIS_LINES)


def test_nothing_shown_to_the_person_claims_safety_gives_a_diagnosis_or_shows_a_label():
    for s in _all_user_facing_strings():
        for pat in BANNED:
            assert not re.search(pat, s, re.IGNORECASE), (pat, s)


def test_the_reviewer_note_says_low_is_not_zero_risk_and_never_the_reverse():
    note = sp.plan_support(CALM, low()).reviewer_note
    assert "LOWER ESTIMATED URGENCY, NOT ZERO RISK" in note
    assert not re.search(r"\bis safe\b|\bno risk\b|\bcleared and\b", note, re.IGNORECASE)


# --- reviewer escalation -----------------------------------------------------------------------------------------------------------

def test_a_reviewer_can_raise_a_low_case_to_medium_or_high_with_a_reason():
    r = low()
    m = sp.escalate(r, "medium", "mentions giving things away in the second paragraph")
    assert m.urgency == "medium" and m.needs_human and m.route == "human_reviewer" and m.risk_score >= 1.0
    assert any("escalated by a reviewer to medium" in x for x in m.reasons)
    h = sp.escalate(m, "high", "contradicts earlier answer about safety plan")
    assert h.urgency == "high" and h.risk_score >= 2.0
    p = sp.plan_support(CALM, h)
    assert p.urgent_protocol and p.show_crisis_resources                     # escalation flows through to the urgent response


def test_escalation_only_raises_and_needs_a_reason():
    r = low()
    for bad in ("low", "urgent", ""):
        with pytest.raises(ValueError):
            sp.escalate(r, bad, "x")
    with pytest.raises(ValueError):
        sp.escalate(r, "medium", "   ")
    high = decide(SURE_HIGH, CALM, policy=V1_POLICY)
    with pytest.raises(ValueError, match="only raises"):
        sp.escalate(high, "medium", "downgrade attempt")
    assert r.urgency == "low"                                                # the original result is untouched


# --- context: the matcher must not be fooled by negation, idioms, or someone else's problem -----------------------------------------------

def topics(text):
    return sp.match_topics(text)


def test_negation_and_positive_follow_ups_do_not_create_a_topic():
    assert topics("I am not stressed about exams anymore, they went well") == ()
    assert topics("My sleep is fine and I have no money worries") == ()
    assert "academic_stress" not in topics("There are no exams this month")


def test_cant_stop_worrying_still_counts_and_cant_sleep_counts_as_sleep():
    t = topics("I can't stop worrying about my exams")
    assert "anxiety_worry" in t and "academic_stress" in t
    assert topics("I can't sleep at night")[0] == "sleep" and topics("I am not sleeping well lately")[0] == "sleep"


def test_everyday_idioms_are_not_mistaken_for_distress():
    for text in ["I like to write down my thoughts to calm down", "my laptop is on low battery", "it works fine after the update",
                 "I want to sit down with a good book"]:
        assert topics(text) == (), text


def test_tired_of_everything_is_low_mood_not_a_sleep_problem():
    t = topics("I am so tired of everything")
    assert t[0] == "low_mood" and "sleep" not in t


def test_no_friends_is_loneliness_not_a_relationship_problem():
    t = topics("I have no friends here")
    assert t[0] == "loneliness" and "relationships" not in t


def test_describing_someone_else_gets_support_for_supporting_them_not_the_writers_own_symptoms():
    t = topics("My friend is lonely and not sleeping, how can I help?")
    assert t == ("supporting_others",)
    both = topics("I am worried about my friend, she is not eating")
    assert both[0] == "supporting_others" and "anxiety_worry" in both
    p = plan("My friend is lonely and not sleeping, how can I help?")
    assert p.intro.startswith("It sounds like you are worried about someone you care about") and p.match_confidence == "clear"


def test_stronger_evidence_wins_and_ties_are_deterministic():
    d = sp.explain_topics("exams exams deadlines and a bit of money stress")
    assert d[0]["topic"] == "academic_stress" and d[0]["score"] > d[-1]["score"]
    assert sp.explain_topics("exams and money worries and I can't sleep") == sp.explain_topics("exams and money worries and I can't sleep")


def test_thin_evidence_is_tentative_and_adds_general_support_instead_of_guessing():
    p = plan("I feel a bit tired")
    assert p.match_confidence == "tentative" and p.intro == sp.GENERAL.intro
    assert any(item in p.self_help for item in sp.GENERAL.self_help)
    n = plan("The weather turned colder this week")
    assert n.match_confidence == "none" and n.topics == ("general",)
    assert plan("I have exams next week and I am struggling to study").match_confidence == "clear"


def test_matcher_survives_odd_input():
    for text in ["", " ", "!!!", "x" * 20000, "😀" * 500, "I " * 3000, "\n\n\t", "नमस्ते मैं ठीक नहीं हूँ"]:
        assert isinstance(sp.match_topics(text), tuple)
        assert sp.plan_support(text, low(text)).human_review_required


def test_probe_regressions_found_by_trying_to_break_the_matcher():
    assert topics("I haven't been sleeping and I just feel empty")[:2] == ("sleep", "low_mood") or set(topics("I haven't been sleeping and I just feel empty")) >= {"sleep", "low_mood"}
    assert "work_money" in topics("My dad lost his job and we can't pay rent")                   # "can't" is the problem, not a denial of it
    assert topics("I used to be anxious but I am much better now") == ()                        # past, and better
    mother = topics("my mother died last month and I can't stop crying")
    assert "supporting_others" not in mother and "grief" in mother and "low_mood" in mother      # the writer is the one grieving
    assert topics("She told me she is thinking of hurting herself") == ("supporting_others",)
    assert topics("Everything feels pointless")[0] == "low_mood"
    assert "anxiety_worry" in topics("I'm so scared about everything")


# --- a message that itself raises a safety signal gets support and helplines, not tips ------------------------------------------------------------------

def test_a_message_with_concerning_language_gets_no_self_help_tips_but_keeps_support_and_helplines():
    for text in ["Nobody would notice if I was gone", "I can't take it anymore", "I have exams and nobody would care if I disappeared"]:
        p = plan(text)
        assert not p.urgent_protocol and p.show_crisis_resources and p.crisis_lines == sp.CRISIS_LINES, text
        assert p.self_help == () and p.intro == sp.FLAGGED_INTRO and p.reach_out, text
        assert p.human_review_required


def test_a_calm_message_from_someone_whose_check_in_raised_a_flag_keeps_its_advice_and_gets_helplines():
    p = plan("I have exams next week and I am struggling to study", floor="medium")
    assert p.show_crisis_resources and p.self_help and p.topics[0] == "academic_stress" and not p.urgent_protocol


def test_a_message_about_someone_elses_risk_keeps_the_supporting_content_and_helplines():
    p = plan("My friend said he wants to kill himself")
    assert p.topics[0] == "supporting_others" and p.show_crisis_resources and p.self_help
    assert any("112" in r for r in p.reach_out)


def test_explicit_first_person_statements_about_ending_ones_life_get_the_urgent_response_not_just_helplines():
    for text in ["I want to die", "I have been thinking about ending my life, and I don't know what to do", "sometimes I just want to die"]:
        p = plan(text)
        assert p.urgent_protocol and p.layout == "help_now" and p.show_crisis_resources and not p.self_help, text
        assert p.crisis_lead == sp.CRISIS_LEAD_URGENT and "URGENT" in p.reviewer_note


def test_each_plan_says_how_to_present_it_and_carries_tap_to_call_helplines_when_a_safety_layer_fired():
    assert plan("I have exams next week and I am struggling to study").layout == "tips"
    assert plan("I have exams next week and I am struggling to study").helplines == ()
    flagged = plan("Nobody would notice if I was gone")
    assert flagged.layout == "support" and flagged.helplines == sp.HELPLINES
    assert plan("I am going to kill myself tonight").layout == "help_now"
    assert plan("I had a great day with my friends").layout == "celebrate"


# --- the check-in floor decides priority; only the MESSAGE decides how alarming the reply is ------------------------------------------------------------

def test_a_calm_or_good_message_from_a_high_floor_person_gets_a_calm_reply():
    for text, layout in [("yah i am feeling better", "celebrate"), ("I had a great day at college", "celebrate"), (CALM, "tips")]:
        r = decide(SURE_LOW, text, "high", V1_POLICY)
        p = sp.plan_support(text, r)
        assert r.urgency == "high" and not r.message_urgent and r.needs_human, text      # still High in the queue, still read by a person
        assert p.layout == layout and not p.urgent_protocol and p.helplines, text


def test_a_concerning_message_from_a_high_floor_person_is_still_urgent():
    for text in ["I want to die", "I am going to kill myself tonight", "I have been thinking about ending my life"]:
        r = decide(SURE_LOW, text, "high", V1_POLICY)
        p = sp.plan_support(text, r)
        assert r.message_urgent and p.urgent_protocol and p.layout == "help_now", text


def test_message_urgency_is_false_for_a_floor_only_case_and_true_when_a_reviewer_raises_it():
    r = decide(SURE_LOW, CALM, "high", V1_POLICY)
    assert not r.message_urgent
    low = decide(SURE_LOW, CALM, "none", V1_POLICY)
    assert sp.escalate(low, "medium", "doubt").message_urgent is False
    assert sp.escalate(low, "high", "warning signs").message_urgent is True


def test_urgent_replies_respond_to_time_and_means_without_promising_anything():
    from iris_ml.demo import triage_payload
    base = triage_payload("I want to kill myself")["reply"]["reach_out"]
    assert base == [sp.URGENT_REACH_OUT]
    soon = triage_payload("I'm going to kill myself tonight")["reply"]["reach_out"]
    assert soon[0] == sp.URGENT_REACH_OUT_SOON and sp.URGENT_REACH_OUT in soon
    means = triage_payload("I want to kill myself, I have pills")["reply"]["reach_out"]
    assert sp.URGENT_REACH_OUT_MEANS in means
    for line in (sp.URGENT_REACH_OUT_SOON, sp.URGENT_REACH_OUT_MEANS):
        assert not re.search(r"promise|will (?:come|call|be there)|help is|safe|minutes|hours", line, re.IGNORECASE), line


def test_the_listening_line_varies_across_messages_but_is_stable_for_one_message():
    from iris_ml.support import LISTENING_VARIANTS, listening_line
    texts = ["I feel lonely", "I cannot sleep", "work is a lot", "I miss home", "exams are close", "I argued with a friend", "I feel flat"]
    lines = {listening_line(t) for t in texts}
    assert len(lines) > 1 and lines <= set(LISTENING_VARIANTS)
    assert listening_line("I feel lonely") == listening_line("  I feel LONELY ")


def test_a_weak_topic_match_gets_general_ideas_not_that_topics_tip():
    p = plan("I'm dying to know my results")
    assert p.match_confidence == "tentative"
    assert all(item in sp.GENERAL.self_help for item in p.self_help)
    assert not any(t == "Study planning" for t, _ in p.self_help)
