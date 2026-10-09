"""The clinical-review package: it must match the code, cover every topic, and make no claim that a clinician has approved anything or that anyone is safe."""
import csv
import io
import json

import numpy as np
import pytest

from iris_ml import support as sp
from iris_ml import support_review as rv
from iris_ml.decision import V1_POLICY, decide

SURE_LOW = np.array([0.95, 0.04, 0.01])
OUTPUTS = [SURE_LOW, np.array([0.05, 0.90, 0.05]), np.array([0.02, 0.08, 0.90]), np.array([0.40, 0.35, 0.25]), None]

MSGS = rv.message_rows()
SCEN = {s["scenario_id"]: s for s in rv.scenario_rows()}
USER_MSGS = [m for m in MSGS if m["audience"] == "user"]


# --- the dataset ------------------------------------------------------------------------------------------------------------------------

def test_every_message_has_a_unique_id_and_all_required_columns():
    assert len({m["message_id"] for m in MSGS}) == len(MSGS) and len({m["recommended_response"] for m in MSGS}) == len(MSGS)
    need = {"message_id", "support_topic", "triggering_keywords_or_context", "recommended_response", "intended_user_situation", "safety_considerations",
            "potential_risks_or_limitations", "review_status", "dismissive_risk", "implies_diagnosis", "unsupported_promise", "inappropriate_advice_risk",
            "delays_urgent_help", "automatic_wording_checks", *rv.CLINICIAN_COLUMNS}
    for m in MSGS:
        assert need <= set(m), m["message_id"]
        for k in need - set(rv.CLINICIAN_COLUMNS):
            assert str(m[k]).strip(), (m["message_id"], k)


def test_every_support_category_is_covered_with_an_opening_self_help_and_a_person_to_contact():
    wanted = {"academic_stress", "loneliness", "sleep", "anxiety_worry", "low_mood", "work_money", "relationships", "grief", "practical_help", "general"}
    assert wanted <= set(rv.TOPIC_META)
    for t in wanted | {"supporting_others"}:
        types = {m["message_type"] for m in MSGS if t in m["support_topic"].split("; ")}
        assert {"topic_intro", "self_help", "reach_out"} <= types, (t, types)
    for kind in ("active_listening", "closing", "emergency_footer", "crisis_resource", "crisis_lead_in", "urgent_response", "reviewer_note", "escalation_record"):
        assert any(m["message_type"] == kind for m in MSGS), kind


def test_nothing_is_marked_approved_and_the_clinician_columns_are_blank():
    for m in MSGS:
        assert m["review_status"] == sp.REVIEW_STATUS == "AI-assisted draft - clinical review pending"
        assert all(m[c] == "" for c in rv.CLINICIAN_COLUMNS), m["message_id"]
    for s in SCEN.values():
        assert s["review_status"] == sp.REVIEW_STATUS
    blob = " ".join(m["recommended_response"] + m["safety_considerations"] for m in MSGS).lower()
    for phrase in ("clinically approved", "approved by", "clinically validated", "safe for deployment", "ready for deployment", "guaranteed"):
        assert phrase not in blob, phrase


def test_every_user_facing_message_passes_the_automatic_wording_checks():
    for m in USER_MSGS:
        assert rv.lint(m["recommended_response"]) == [], (m["message_id"], rv.lint(m["recommended_response"]))
        assert m["automatic_wording_checks"] == "pass"


def test_the_wording_checks_actually_catch_bad_wording():
    for text, kind in [("You are safe now", "safety_claim"), ("There is no risk here", "safety_claim"), ("You have depression", "diagnosis"),
                       ("Just relax and cheer up", "minimizing"), ("You should always try harder", "directive"), ("This will fix everything", "promise"),
                       ("Your priority is low", "label_leak")]:
        assert kind in rv.lint(text), (text, kind)
    assert rv.lint("Your priority is low", audience="reviewer") == []                    # labels are fine for reviewers, never for the person


def test_checklist_overrides_refer_to_real_messages():
    assert set(rv.OVERRIDES) <= {m["message_id"] for m in MSGS}


def test_every_message_type_has_context_text():
    for m in MSGS:
        for table in (rv.TYPE_SITUATION, rv.TYPE_SAFETY, rv.TYPE_LIMITS):
            assert m["message_type"] in table


# --- every response maps to the right topic ------------------------------------------------------------------------------------------------

def test_every_documented_keyword_really_triggers_its_topic():
    for code, meta in rv.TOPIC_META.items():
        if code in ("general", "positive"):
            continue
        for kw in meta["keywords"]:
            assert code in sp.match_topics(kw, limit=5), (code, kw)


ORDINARY_TOPIC = {"SC39": "supporting_others", "SC40": "academic_stress", "SC41": "loneliness", "SC42": "sleep", "SC43": "anxiety_worry", "SC44": "low_mood",
                  "SC45": "work_money", "SC46": "relationships", "SC47": "grief", "SC48": "practical_help", "SC49": "general"}


@pytest.mark.parametrize("sid,topic", sorted(ORDINARY_TOPIC.items()))
def test_each_ordinary_scenario_gets_its_own_topics_wording(sid, topic):
    text = SCEN[sid]["example_message"]
    plan = sp.plan_support(text, decide(SURE_LOW, text, "none", V1_POLICY))
    assert plan.topics[0] == topic
    by_name = {t.name: t for t in sp.ALL_TOPICS}
    if plan.match_confidence == "clear":
        assert plan.intro == by_name[topic].intro
    assert plan.human_review_required and not plan.urgent_protocol


def test_every_sentence_a_person_can_be_shown_is_in_the_reviewed_list():
    allowed = {m["recommended_response"] for m in MSGS if m["audience"] == "user"}
    texts = [s["example_message"] for s in SCEN.values()] + ["", "hello", "exams money sleep lonely grief", "x" * 500]
    for text in texts:
        for probs in OUTPUTS:
            for floor in ("none", "medium", "high"):
                p = sp.plan_support(text, decide(probs, text, floor, V1_POLICY))
                shown = [p.intro, p.listening, p.closing, p.emergency_footer, *p.reach_out, *p.crisis_lines, *[f"{a}: {b}" for a, b in p.self_help]]
                if p.crisis_lead:
                    shown.append(p.crisis_lead)
                for s in shown:
                    assert s in allowed, (text, s)


# --- safety-critical scenarios ------------------------------------------------------------------------------------------------------------------

URGENT_IDS = ["SC01", "SC02", "SC03", "SC04", "SC05", "SC06", "SC07", "SC08", "SC09", "SC09b", "SC37", "SC56"]


@pytest.mark.parametrize("sid", URGENT_IDS)
@pytest.mark.parametrize("floor", ["none", "medium", "high"])
def test_explicit_and_imminent_cases_get_the_urgent_workflow_whatever_a_model_predicts(sid, floor):
    text = SCEN[sid]["example_message"]
    for probs in OUTPUTS:
        r = decide(probs, text, floor, V1_POLICY)
        p = sp.plan_support(text, r)
        assert p.urgent_protocol and p.show_crisis_resources and p.crisis_lines == sp.CRISIS_LINES
        assert not p.self_help and r.needs_human and r.urgency == "high"                  # no self-help in place of help


def test_the_check_in_floor_alone_makes_the_case_High_for_reviewers_without_an_alarming_reply():
    text = "The weather turned colder this week"
    r = decide(SURE_LOW, text, "high", V1_POLICY)
    p = sp.plan_support(text, r)
    assert r.urgency == "high" and not r.message_urgent and r.needs_human
    assert not p.urgent_protocol and p.layout == "tips" and p.show_crisis_resources and p.crisis_lead == sp.CRISIS_LEAD_FLAGGED


def test_ordinary_support_never_triggers_the_urgent_workflow_and_urgent_never_looks_ordinary():
    for sid, s in SCEN.items():
        if s["desired_workflow"] == rv.ORD and s["status"] != "known_gap":
            assert s["observed_workflow"] == rv.ORD, sid
    for sid in URGENT_IDS:
        assert SCEN[sid]["observed_workflow"] == rv.URG


def test_every_scenario_is_mandatory_human_review_even_when_the_model_says_low():
    assert all(s["human_review_mandatory"] == "yes" for s in SCEN.values())


def test_the_scenario_set_covers_every_required_kind_of_message():
    cats = " | ".join(s["category"] for s in SCEN.values()).lower()
    for kind in ("explicit", "indirect", "ambiguous", "negation", "past", "another person", "idiom", "ordinary"):
        assert kind in cats, kind


def test_covered_scenarios_behave_as_desired_and_the_known_gaps_are_exactly_the_documented_ones():
    for sid, s in SCEN.items():
        if s["status"] == "covered":
            assert s["observed_workflow"] == s["desired_workflow"], sid
    gaps = {sid for sid, s in SCEN.items() if s["status"] == "known_gap"}
    # If you close a gap, this test fails on purpose: update the list, the notes and the status document together.
    assert gaps == {"SC21", "SC23"}              # SC19, SC20, SC22, SC25 and SC38 were closed after review and hand testing
    for sid in gaps:
        assert SCEN[sid]["observed_workflow"] != SCEN[sid]["desired_workflow"]
        assert SCEN[sid]["human_review_mandatory"] == "yes"                                 # a person still reads it


def test_questions_for_the_clinician_are_recorded_where_behaviour_is_a_judgement_call():
    needs = {sid for sid, s in SCEN.items() if s["status"] == "clinician_decision_needed"}
    assert {"SC08", "SC13", "SC33", "SC24"} <= needs
    assert all(SCEN[sid]["question_for_clinician"] for sid in needs)


# --- nothing claims safety ------------------------------------------------------------------------------------------------------------------------

def test_no_plan_for_any_scenario_claims_the_person_is_safe():
    for s in SCEN.values():
        text = s["example_message"]
        p = sp.plan_support(text, decide(SURE_LOW, text, "none", V1_POLICY))
        blob = sp.user_facing_text(p)
        assert not rv.LINTS["safety_claim"].search(blob) and not rv.LINTS["diagnosis"].search(blob), text
        assert "safe" not in blob.lower() and "no risk" not in blob.lower()


def test_the_reviewer_is_told_low_is_not_zero_risk_in_the_dataset():
    low = next(m for m in MSGS if m["message_id"] == "SM-REVIEWER-LOW")
    assert "NOT ZERO RISK" in low["recommended_response"] and "not cleared" in low["recommended_response"]


# --- the files on disk are exactly what the code produces ---------------------------------------------------------------------------------------

def test_the_generated_review_files_match_the_code_and_carry_the_draft_banner():
    for name, content in rv.build_all().items():
        disk = (rv.OUT_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert disk == content, f"{name} is out of date: run python -m iris_ml.support_review"
        if name.endswith(".md"):
            assert "AI-ASSISTED DRAFT - CLINICAL REVIEW PENDING" in content
    data = json.loads((rv.OUT_DIR / "support_messages.json").read_text(encoding="utf-8"))
    assert data["review_status"] == sp.REVIEW_STATUS and len(data["rows"]) == len(MSGS)
    rows = list(csv.DictReader(io.StringIO((rv.OUT_DIR / "support_messages.csv").read_text(encoding="utf-8"))))
    assert [r["message_id"] for r in rows] == [m["message_id"] for m in MSGS]


# --- good news gets a warm reply, never advice, and never when anything concerning is present ---------------------------------------------------------------

POSITIVE_IDS = ["SC50", "SC51", "SC52", "SC53", "SC54"]


@pytest.mark.parametrize("sid", POSITIVE_IDS)
def test_good_news_gets_a_warm_reply_with_no_advice_and_no_helplines(sid):
    text = SCEN[sid]["example_message"]
    p = sp.plan_support(text, decide(SURE_LOW, text, "none", V1_POLICY))
    assert p.layout == "celebrate" and p.topics == ("positive",) and not p.self_help and not p.show_crisis_resources
    assert p.intro in sp.POSITIVE_INTRO.values() and p.listening in sp.POSITIVE_BODY.values() and p.human_review_required   # still read by a person
    assert SCEN[sid]["observed_workflow"] == rv.POS


@pytest.mark.parametrize("sid", ["SC55", "SC56", "SC57"])
def test_mixed_messages_never_get_the_cheerful_reply(sid):
    text = SCEN[sid]["example_message"]
    p = sp.plan_support(text, decide(SURE_LOW, text, "none", V1_POLICY))
    assert p.layout != "celebrate" and p.topics != ("positive",)


def test_good_news_from_someone_whose_check_in_raised_a_flag_still_gets_the_helplines():
    text = SCEN["SC50"]["example_message"]
    p = sp.plan_support(text, decide(SURE_LOW, text, "high", V1_POLICY))
    assert p.layout == "celebrate" and not p.urgent_protocol and p.show_crisis_resources and p.helplines and p.provisional_priority == "high"


def test_helpline_cards_use_exactly_the_numbers_in_the_crisis_lines():
    joined = " ".join(sp.CRISIS_LINES)
    for name, detail, number, tel in sp.HELPLINES:
        assert number in joined and tel.replace("-", "") == number.replace("-", "")


def test_every_status_line_is_in_the_reviewed_list_and_makes_no_promise_of_timing():
    allowed = {m["recommended_response"] for m in MSGS}
    for (state, urgent), line in sp.STATUS_LINES.items():
        assert line in allowed and sp.status_line(state, urgent) == line
        assert rv.lint(line) == [], (state, urgent, rv.lint(line))
        assert "minute" not in line and "doctor" not in line.lower()        # no time and no doctor is ever promised
