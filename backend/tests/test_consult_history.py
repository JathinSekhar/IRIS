"""The person's doctor history (profile page): only their own requests, the doctor's public details once one accepted, and never the clinical note,
risk answers or triage flags."""
from fastapi.testclient import TestClient

from app.main import app
from devtools import demo_data as dd
from tests.test_consult_chat import accepted_case
from tests.test_consult_close import NOTE
from tests.test_messages import env, login, signup  # noqa: F401

NEVER = {"concerns", "observations", "ideation", "plan", "intent", "means_access", "previous_attempt", "protective_factors", "risk_level",
         "safety_plan", "impression", "actions_taken", "follow_up", "follow_up_date", "referral", "urgent", "reason", "flag", "source"}


def test_not_signed_in_has_no_history(env):
    with TestClient(app) as c:
        assert c.get("/api/consults/history").status_code == 401


def test_a_person_with_no_requests_has_an_empty_history(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert c.get("/api/consults/history").json() == []


def test_a_finished_session_shows_the_doctor_and_the_conversation_but_never_the_note(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "Hello, how are you feeling today?"}).status_code == 201
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE).status_code == 200
        login(c, dd.NORMAL.signup)
        [h] = c.get("/api/consults/history").json()
        assert h["id"] == case_id and h["state"] == "closed" and h["ended_at"] and h["message_count"] == 1
        assert h["doctor_name"] == dd.DOCTOR["full_name"] and h["doctor_registration_number"] == dd.DOCTOR_PROFILE["registration_number"]
        assert not NEVER & set(h), NEVER & set(h)
        text = str(h)
        assert NOTE["concerns"] not in text and NOTE["impression"] not in text
        thread = c.get(f"/api/consults/{case_id}/messages").json()            # the conversation stays readable, without flags
        assert [m["text"] for m in thread] == ["Hello, how are you feeling today?"] and all(m["flag"] is None for m in thread)


def test_an_unanswered_or_cancelled_request_names_no_doctor(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        first = c.post("/api/consults", json={"share": True}).json()["id"]
        assert c.post(f"/api/consults/{first}/cancel").status_code == 200
        second = c.post("/api/consults", json={"share": True}).json()["id"]
        rows = c.get("/api/consults/history").json()
        assert [r["id"] for r in rows] == [second, first]                     # newest first
        assert [r["state"] for r in rows] == ["open", "cancelled"]
        assert all(r["doctor_name"] is None and r["doctor_registration_number"] is None for r in rows)


def test_nobody_sees_anyone_elses_history(env):
    with TestClient(app) as c:
        accepted_case(c, env)                                                  # Ananya has a case
        c.post("/api/auth/logout")
        signup(c, dd.MEDIUM.signup, dd.MEDIUM.answers)
        assert c.get("/api/consults/history").json() == []
