"""Step 4 / 4b: a doctor ends a conversation by completing the session form. No form, no close. The suicide-risk questions must each be answered explicitly,
the person is told it ended, the note is clinical and is never shown to them, and a reviewer can read it on request (audited)."""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, ConsultCase, SessionNote
from devtools import demo_data as dd
from tests.test_consult import DOCTOR2, add_doctor
from tests.test_consult_chat import accepted_case, doctor_login
from tests.test_messages import env, login, make_reviewer  # noqa: F401

NOTE = {
    "mode": "chat", "concerns": "Poor sleep for two weeks, feels like a burden.", "observations": "Wrote in short sentences, appeared tired.",
    "ideation": "no", "plan": "no", "intent": "no", "means_access": "not_assessed", "previous_attempt": "no",
    "protective_factors": "Supportive roommate, wants to finish the semester.", "risk_level": "medium",
    "safety_plan": "created", "safety_plan_copy_given": True, "impression": "Low mood with sleep disturbance; needs follow-up.",
    "actions_taken": "Listened, discussed sleep routine, safety planning discussed.", "follow_up": "Check in again in three days.",
    "follow_up_date": (date.today() + timedelta(days=3)).isoformat(), "referral": "College counsellor", "emergency_services_contacted": False,
}


def test_a_conversation_cannot_be_closed_without_the_form(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={}).status_code == 422
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={**NOTE, "concerns": "  "}).status_code == 422
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={**NOTE, "risk_level": "fine"}).status_code == 422
    with env() as s:
        assert s.get(ConsultCase, case_id).state == "in_session"


def test_every_risk_question_must_be_answered_explicitly(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        for field in ("ideation", "plan", "intent", "means_access", "previous_attempt", "safety_plan", "protective_factors"):
            body = {k: v for k, v in NOTE.items() if k != field}
            assert c.post(f"/api/doctor/cases/{case_id}/close", json=body).status_code == 422, field
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={**NOTE, "ideation": "maybe"}).status_code == 422
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={**NOTE, "safety_plan": "done"}).status_code == 422


def test_the_follow_up_date_cannot_be_in_the_past(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        past = {**NOTE, "follow_up_date": (date.today() - timedelta(days=1)).isoformat()}
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=past).status_code == 422
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={k: v for k, v in NOTE.items() if k != "follow_up_date"}).status_code == 200


def test_closing_saves_the_note_ends_the_conversation_and_the_person_is_told(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        r = c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE)
        assert r.status_code == 200
        out = r.json()
        assert out["risk_level"] == "medium" and out["doctor_name"] == dd.DOCTOR["full_name"] and out["means_access"] == "not_assessed"
        assert out["safety_plan"] == "created" and out["safety_plan_copy_given"] is True and out["follow_up_date"] == NOTE["follow_up_date"]
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE).status_code == 409          # only once
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "one more thing"}).status_code == 409
        assert c.get(f"/api/doctor/cases/{case_id}/note").json()["follow_up"] == NOTE["follow_up"]
        assert any(x["state"] == "closed" for x in c.get("/api/doctor/cases").json())
        login(c, dd.NORMAL.signup)
        assert c.get("/api/consults/current").json() is None
        assert c.post(f"/api/consults/{case_id}/messages", json={"text": "thanks"}).status_code == 409
        assert c.get(f"/api/consults/{case_id}/messages").status_code == 200
    with env() as s:
        assert s.get(ConsultCase, case_id).state == "closed" and s.get(SessionNote, case_id) is not None
        assert "close_case" in [a.action for a in s.scalars(select(AuditLog))]


def test_the_person_never_gets_the_clinical_note(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE)
        login(c, dd.NORMAL.signup)
        for path in (f"/api/doctor/cases/{case_id}/note", f"/api/reviewer/consults/{case_id}/note", f"/api/doctor/cases/{case_id}"):
            assert c.get(path).status_code == 403


def test_only_the_owning_doctor_can_close_read_the_note_or_see_the_person_details(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        add_doctor(c, env, DOCTOR2)
        doctor_login(c, DOCTOR2)
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE).status_code == 404
        assert c.get(f"/api/doctor/cases/{case_id}/note").status_code == 404
        assert c.get(f"/api/doctor/cases/{case_id}").status_code == 404


def test_a_reviewer_can_read_the_note_on_request_and_it_is_audited(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE)
        make_reviewer(c, env)
        got = c.get(f"/api/reviewer/consults/{case_id}/note").json()
        assert got["concerns"] == NOTE["concerns"] and got["ideation"] == "no" and got["safety_plan"] == "created"
    with env() as s:
        assert "view_session_note" in [a.action for a in s.scalars(select(AuditLog))]


def test_the_doctor_sees_who_they_are_speaking_with_and_whether_it_is_a_minor(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        d = c.get(f"/api/doctor/cases/{case_id}").json()
        assert d["full_name"] == dd.NORMAL.signup["full_name"] and d["is_minor"] is False and d["age"] >= 18
        assert d["phone"] and d["emergency_contact"]
    with env() as s:
        assert "view_case_detail" in [a.action for a in s.scalars(select(AuditLog))]


def test_a_minor_is_flagged_on_the_offer_and_the_case(env):
    from tests.test_consult import ask
    minor = {**dd.NORMAL.signup, "email": "minor.test@example.com", "date_of_birth": f"{date.today().year - 15}-03-02",
             "guardian_name": "Suresh Rao", "guardian_email": "guardian@example.com"}
    with TestClient(app) as c:
        c.post("/api/auth/register", json=minor)
        c.post("/api/consent", json={"version": "2026-10"})
        case_id = ask(c).json()["id"]
        add_doctor(c, env)
        doctor_login(c)
        assert c.get("/api/doctor/offers").json()[0]["is_minor"] is True
        assert c.post(f"/api/doctor/offers/{case_id}/accept").status_code == 200
        d = c.get(f"/api/doctor/cases/{case_id}").json()
        assert d["is_minor"] is True and d["guardian_name"] == "Suresh Rao"


def test_the_person_sees_the_doctors_registration_number_once_accepted(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        login(c, dd.NORMAL.signup)
        cur = c.get("/api/consults/current").json()
        assert cur["id"] == case_id and cur["doctor_registration_number"].startswith("TEST-") and cur["doctor_specialty"]
