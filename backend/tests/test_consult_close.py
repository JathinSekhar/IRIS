"""Step 4: a doctor ends a conversation by completing the session form. No form, no close. The person is told it ended; the note is clinical and is never
shown to them; a reviewer can read it on request (audited)."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, ConsultCase, SessionNote
from devtools import demo_data as dd
from tests.test_consult import DOCTOR2, add_doctor
from tests.test_consult_chat import accepted_case, doctor_login
from tests.test_messages import env, login, make_reviewer  # noqa: F401

NOTE = {"mode": "chat", "concerns": "Poor sleep for two weeks, feels like a burden.", "risk_level": "medium",
        "actions_taken": "Listened, discussed sleep routine, safety planning discussed.", "follow_up": "Check in again in three days.",
        "referral": "College counsellor", "emergency_services_contacted": False}


def test_a_conversation_cannot_be_closed_without_the_form(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={}).status_code == 422
        bad = {**NOTE, "concerns": "  "}
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=bad).status_code == 422
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={**NOTE, "risk_level": "fine"}).status_code == 422
    with env() as s:
        assert s.get(ConsultCase, case_id).state == "accepted"


def test_closing_saves_the_note_ends_the_conversation_and_the_person_is_told(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        r = c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE)
        assert r.status_code == 200 and r.json()["risk_level"] == "medium" and r.json()["doctor_name"] == dd.DOCTOR["full_name"]
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE).status_code == 409          # only once
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "one more thing"}).status_code == 409
        assert c.get(f"/api/doctor/cases/{case_id}/note").json()["follow_up"] == NOTE["follow_up"]
        assert any(x["state"] == "closed" for x in c.get("/api/doctor/cases").json())
        login(c, dd.NORMAL.signup)
        assert c.get("/api/consults/current").json() is None                                          # nothing live: they can ask again
        assert c.post(f"/api/consults/{case_id}/messages", json={"text": "thanks"}).status_code == 409
        assert c.get(f"/api/consults/{case_id}/messages").status_code == 200                           # they can still read the conversation
    with env() as s:
        assert s.get(ConsultCase, case_id).state == "closed" and s.get(SessionNote, case_id) is not None
        assert "close_case" in [a.action for a in s.scalars(select(AuditLog))]


def test_the_person_never_gets_the_clinical_note(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE)
        login(c, dd.NORMAL.signup)
        for path in (f"/api/doctor/cases/{case_id}/note", f"/api/reviewer/consults/{case_id}/note"):
            assert c.get(path).status_code == 403


def test_only_the_owning_doctor_can_close_or_read_the_note(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        add_doctor(c, env, DOCTOR2)
        doctor_login(c, DOCTOR2)
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE).status_code == 404
        assert c.get(f"/api/doctor/cases/{case_id}/note").status_code == 404


def test_a_reviewer_can_read_the_note_on_request_and_it_is_audited(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE)
        make_reviewer(c, env)
        assert c.get(f"/api/reviewer/consults/{case_id}/note").json()["concerns"] == NOTE["concerns"]
    with env() as s:
        assert "view_session_note" in [a.action for a in s.scalars(select(AuditLog))]
