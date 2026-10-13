"""The doctor starts the conversation: accepted -> in_session. Until then chat and video are closed for both sides and the person is told the truth.
Plus the doctor's summary: rules-based bullets that never leave the server, and an AI draft that needs the person's separate agreement."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models import AuditLog, ConsultCase
from app.services import case_summary, consult
from devtools import demo_data as dd
from tests.test_consult import DOCTOR2, add_doctor
from tests.test_consult_chat import accepted_case, doctor_login
from tests.test_messages import CALM, SELF_HARM, env, login, send  # noqa: F401


def test_after_accept_nobody_can_chat_or_call_until_the_doctor_starts(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env, started=False)
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "hello"}).status_code == 409
        assert c.post(f"/api/doctor/cases/{case_id}/call", json={"kind": "request"}).status_code == 409
        login(c, dd.NORMAL.signup)
        r = c.post(f"/api/consults/{case_id}/messages", json={"text": "hello?"})
        assert r.status_code == 409 and "when they are ready" in r.json()["detail"]
        assert c.post(f"/api/consults/{case_id}/call", json={"kind": "request"}).status_code == 409
        cur = c.get("/api/consults/current").json()
        assert cur["state"] == "accepted" and cur["doctor_name"] == dd.DOCTOR["full_name"] and cur["status_text"] == consult.STATUS_ACCEPTED


def test_starting_opens_the_conversation_and_tells_the_person(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env, started=False)
        assert c.post(f"/api/doctor/cases/{case_id}/start").json()["state"] == "in_session"
        assert c.post(f"/api/doctor/cases/{case_id}/start").status_code == 200          # starting twice changes nothing
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "hello"}).status_code == 201
        login(c, dd.NORMAL.signup)
        assert c.get("/api/consults/current").json()["status_text"] == consult.STATUS_IN_SESSION
        assert c.post(f"/api/consults/{case_id}/messages", json={"text": "hi doctor"}).status_code == 201
    with env() as s:
        assert s.get(ConsultCase, case_id).started_at is not None
        assert "start_case" in [a.action for a in s.scalars(select(AuditLog))]


def test_only_the_owning_doctor_can_start_and_a_closed_case_cannot_be_started(env):
    from tests.test_consult_close import NOTE

    with TestClient(app) as c:
        case_id = accepted_case(c, env, started=False)
        add_doctor(c, env, DOCTOR2)
        doctor_login(c, DOCTOR2)
        assert c.post(f"/api/doctor/cases/{case_id}/start").status_code == 404
        doctor_login(c)
        assert c.post(f"/api/doctor/cases/{case_id}/close", json=NOTE).status_code == 200      # a doctor may close without starting
        assert c.post(f"/api/doctor/cases/{case_id}/start").status_code == 409


def test_a_patient_cannot_start_a_conversation(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env, started=False)
        login(c, dd.NORMAL.signup)
        assert c.post(f"/api/doctor/cases/{case_id}/start").status_code == 403


# ---- the summary ---------------------------------------------------------------------------------------------------------------------------------
def test_the_rules_based_summary_shows_profile_checkin_and_chat_and_is_audited(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env, started=False)
        login(c, dd.NORMAL.signup)
        send(c, CALM)
        send(c, SELF_HARM)
        doctor_login(c)
        s = c.get(f"/api/doctor/cases/{case_id}/summary").json()
        text = " ".join(s["bullets"])
        assert s["profile"]["first_name"] == "Ananya" and s["checkin"]["baseline_risk"] == "low" and s["checkin"]["phq9"] is not None
        assert "2 recent messages" in text and "1 explicit" in text and "study or exam pressure" in text
        assert [m["text"] for m in s["recent_messages"]] == [CALM, SELF_HARM]
        assert s["ai_allowed"] is False and s["ai_summary"] is None
        assert "phone" not in str(s).lower() and "@" not in str(s)
    with env() as s_:
        assert "view_summary" in [a.action for a in s_.scalars(select(AuditLog))]


def test_another_doctor_and_the_patient_cannot_read_the_summary(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        add_doctor(c, env, DOCTOR2)
        doctor_login(c, DOCTOR2)
        assert c.get(f"/api/doctor/cases/{case_id}/summary").status_code == 404
        login(c, dd.NORMAL.signup)
        assert c.get(f"/api/doctor/cases/{case_id}/summary").status_code == 403


def test_the_ai_draft_needs_the_persons_separate_agreement(env, monkeypatch):
    called = []
    monkeypatch.setattr(case_summary, "draft_ai", lambda db, case: called.append(case.id) or "should not be used")
    with TestClient(app) as c:
        case_id = accepted_case(c, env, share_ai=False)
        assert c.post(f"/api/doctor/cases/{case_id}/summary/ai").status_code == 403
    assert called == []


def test_the_ai_draft_is_stored_labelled_and_audited_when_the_person_agreed(env, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")
    monkeypatch.setattr(case_summary, "draft_ai", lambda db, case: "Sleeps badly and feels like a burden; no plan stated.")
    with TestClient(app) as c:
        case_id = accepted_case(c, env, share_ai=True)
        out = c.post(f"/api/doctor/cases/{case_id}/summary/ai").json()
        assert out["ai_summary"].startswith("Sleeps badly") and out["ai_disclosure"].startswith("AI-assisted draft")
        assert c.get(f"/api/doctor/cases/{case_id}/summary").json()["ai_summary"] == out["ai_summary"]
    with env() as s:
        assert "ai_summary_ok" in [a.action for a in s.scalars(select(AuditLog))]


def test_an_ai_failure_leaves_the_rules_based_summary_working(env, monkeypatch):
    monkeypatch.setattr(case_summary, "draft_ai", lambda db, case: None)
    with TestClient(app) as c:
        case_id = accepted_case(c, env, share_ai=True)
        assert c.post(f"/api/doctor/cases/{case_id}/summary/ai").status_code == 503
        assert c.get(f"/api/doctor/cases/{case_id}/summary").status_code == 200
    with env() as s:
        assert "ai_summary_failed" in [a.action for a in s.scalars(select(AuditLog))]


def test_only_the_minimum_is_sent_to_the_ai(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env, share_ai=True)
        login(c, dd.NORMAL.signup)
        send(c, CALM)
    with env() as s:
        text = case_summary.payload_text(s, s.get(ConsultCase, case_id))
    for private in (dd.NORMAL.signup["full_name"], dd.NORMAL.signup["email"], dd.NORMAL.signup["phone"], dd.NORMAL.signup["emergency_contact"]):
        assert private not in text
    assert CALM in text and "age" in text


def test_the_ai_output_check_rejects_empty_and_long_text(monkeypatch):
    class R:
        def __init__(self, content):
            self._c = content

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": self._c}}]}

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")
    monkeypatch.setattr(case_summary, "payload_text", lambda db, case: "x")
    for content in ("", "word " * 400):
        monkeypatch.setattr(case_summary.httpx, "post", lambda *a, _c=content, **k: R(_c))
        assert case_summary.draft_ai(None, None) is None
    monkeypatch.setattr(case_summary.httpx, "post", lambda *a, **k: R("Short factual summary."))
    assert case_summary.draft_ai(None, None) == "Short factual summary."
