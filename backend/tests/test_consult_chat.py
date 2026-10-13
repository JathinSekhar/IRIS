"""Step 3: the conversation between a person and the doctor who accepted their case. Only those two can use it; a reviewer can read it on request
(audited); the rule flag on a worrying line is seen by the doctor, never by the person; nothing here is written by a model."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, ConsultMessage
from devtools import demo_data as dd
from tests.test_consult import DOCTOR2, add_doctor, ask
from tests.test_messages import env, login, make_reviewer, signup  # noqa: F401


def doctor_login(c, data=dd.DOCTOR):
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"email": data["email"], "password": data["password"]}).status_code == 200


def accepted_case(c, env, started=True, share_ai=False):
    """A person asked, a doctor accepted and (by default) began the conversation. Leaves the doctor signed in."""
    signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
    case_id = c.post("/api/consults", json={"share": True, "share_ai": share_ai}).json()["id"]
    add_doctor(c, env)
    doctor_login(c)
    assert c.post(f"/api/doctor/offers/{case_id}/accept").status_code == 200
    if started:
        assert c.post(f"/api/doctor/cases/{case_id}/start").status_code == 200
    return case_id


def test_the_person_cannot_write_before_a_doctor_accepts(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        r = c.post(f"/api/consults/{case_id}/messages", json={"text": "hello"})
        assert r.status_code == 409


def test_both_sides_can_talk_and_each_sees_the_same_conversation(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "Hello, I am Dr. Menon. What would you like to talk about?"}).status_code == 201
        login(c, dd.NORMAL.signup)
        r = c.post(f"/api/consults/{case_id}/messages", json={"text": "I have not been sleeping."})
        assert r.status_code == 201 and r.json()["mine"] is True and r.json()["sender_role"] == "user"
        seen = c.get(f"/api/consults/{case_id}/messages").json()
        assert [(m["sender_role"], m["mine"]) for m in seen] == [("doctor", False), ("user", True)]
        doctor_login(c)
        seen = c.get(f"/api/doctor/cases/{case_id}/messages").json()
        assert [(m["sender_role"], m["mine"]) for m in seen] == [("doctor", True), ("user", False)]


def test_a_worrying_line_is_flagged_for_the_doctor_but_never_shown_to_the_person(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        login(c, dd.NORMAL.signup)
        c.post(f"/api/consults/{case_id}/messages", json={"text": "I am thinking of killing myself"})
        mine = c.get(f"/api/consults/{case_id}/messages").json()
        assert all(m["urgent"] is False for m in mine)
        doctor_login(c)
        assert c.get(f"/api/doctor/cases/{case_id}/messages").json()[0]["urgent"] is True


def test_another_doctor_and_another_person_cannot_read_or_write(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        add_doctor(c, env, DOCTOR2)
        doctor_login(c, DOCTOR2)
        assert c.get(f"/api/doctor/cases/{case_id}/messages").status_code == 404
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "hi"}).status_code == 404
        c.post("/api/auth/logout")
        signup(c, dd.HIGH.signup, dd.HIGH.answers)
        assert c.get(f"/api/consults/{case_id}/messages").status_code == 404
        assert c.post(f"/api/consults/{case_id}/messages", json={"text": "hi"}).status_code == 404


def test_empty_and_overlong_messages_are_refused(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "   "}).status_code == 422
        assert c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "x" * 2001}).status_code == 422


def test_a_reviewer_can_read_a_conversation_and_it_is_audited(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        c.post(f"/api/doctor/cases/{case_id}/messages", json={"text": "Hello"})
        make_reviewer(c, env)
        assert [m["text"] for m in c.get(f"/api/reviewer/consults/{case_id}/messages").json()] == ["Hello"]
    with env() as s:
        assert "view_consult_thread" in [a.action for a in s.scalars(select(AuditLog))]


def test_a_patient_cannot_use_the_reviewer_thread_route(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        login(c, dd.NORMAL.signup)
        assert c.get(f"/api/reviewer/consults/{case_id}/messages").status_code == 403


def test_opening_a_conversation_is_audited_for_the_doctor(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        c.get(f"/api/doctor/cases/{case_id}/messages")
        c.get(f"/api/doctor/cases/{case_id}/messages")          # a refresh within five minutes is not logged again
    with env() as s:
        n = len([a for a in s.scalars(select(AuditLog)) if a.action == "view_thread"])
        assert n == 1
        assert s.scalars(select(ConsultMessage)).all() == []
