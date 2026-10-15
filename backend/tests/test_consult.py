"""Step 2 of the doctor feature: a person asks for a doctor, on-duty doctors see the request, the first to accept owns it.

The safety rules under test: the person must agree to share first; before a doctor accepts, the status never promises a doctor or a time and the
helplines are present; a request is only visible to its owner and to on-duty doctors; reading it is audited."""
import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, ConsultCase, DoctorProfile, User
from app.services import consult
from devtools import demo_data as dd
from tests.test_messages import CALM, SELF_HARM, env, login, send, signup  # noqa: F401

DOCTOR2 = {**dd.DOCTOR, "full_name": "Dr. Arun Pillai", "email": "doctor.two@example.com"}


def add_doctor(c, env, data=dd.DOCTOR, on_duty=True):
    c.post("/api/auth/logout")
    assert c.post("/api/auth/register", json=data).status_code == 201
    with env() as s:
        u = s.scalar(select(User).where(User.email == data["email"]))
        u.role = "doctor"
        s.add(DoctorProfile(user_id=u.id, on_duty=on_duty, **dd.DOCTOR_PROFILE))
        s.commit()


def ask(c, share=True):
    return c.post("/api/consults", json={"share": share})


def test_a_request_needs_the_person_to_agree_to_share(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        r = ask(c, share=False)
        assert r.status_code == 422
        assert c.get("/api/consults/current").json() is None


def test_before_a_doctor_accepts_the_status_is_honest_and_the_helplines_are_there(env):
    with TestClient(app) as c:
        add_doctor(c, env, on_duty=False)
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        none_on_duty = ask(c).json()
        assert none_on_duty["state"] == "open" and none_on_duty["doctor_name"] is None
        assert none_on_duty["status_text"] == consult.STATUS_NONE_ON_DUTY and none_on_duty["helplines"]
    with env() as s:
        s.scalar(select(DoctorProfile)).on_duty = True
        s.commit()
    with TestClient(app) as c:
        login(c, dd.NORMAL.signup)
        trying = c.get("/api/consults/current").json()
        assert trying["status_text"] == consult.STATUS_TRYING and trying["doctor_name"] is None and trying["helplines"]


def test_the_waiting_status_lines_make_no_promise_about_a_doctor_or_a_time():
    for line in (consult.STATUS_TRYING, consult.STATUS_NONE_ON_DUTY):
        assert not re.search(r"\b(?:will (?:be|call|come|join|reach)|is coming|soon|shortly|minutes?|hours?|within|promise|guarantee)\b", line, re.IGNORECASE), line
        assert "cannot say" in line and "numbers below" in line


def test_asking_twice_returns_the_same_request(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        a, b = ask(c).json(), ask(c).json()
        assert a["id"] == b["id"]


def test_before_accepting_a_doctor_sees_only_what_is_needed_to_decide_and_it_is_audited(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, CALM)
        send(c, SELF_HARM)
        ask(c)
        add_doctor(c, env)
        c.post("/api/auth/logout")
        assert c.post("/api/auth/login", json={"email": dd.DOCTOR["email"], "password": dd.DOCTOR["password"]}).status_code == 200
        offers = c.get("/api/doctor/offers").json()
        assert len(offers) == 1
        o = offers[0]
        assert o["first_name"] == "Ananya" and o["urgent"] is True and o["priority"] == "high"
        assert o["recent_messages"] == []                                     # no message text before accepting: the person shared with "the doctor who accepts"
        assert CALM not in str(o) and SELF_HARM not in str(o)
        assert o["checkin"]["baseline_risk"] == "low" and o["checkin"]["phq9"] is None and o["checkin"]["gad7"] is None
        assert o["age"] >= 18
        assert "email" not in str(o).lower() and "phone" not in str(o).lower()
    with env() as s:
        assert "view_offers" in [a.action for a in s.scalars(select(AuditLog))]


def test_an_off_duty_doctor_is_offered_nothing_and_cannot_accept(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        add_doctor(c, env, on_duty=False)
        c.post("/api/auth/login", json={"email": dd.DOCTOR["email"], "password": dd.DOCTOR["password"]})
        assert c.get("/api/doctor/offers").json() == []
        assert c.post(f"/api/doctor/offers/{case_id}/accept").status_code == 409


def test_the_first_doctor_to_accept_owns_it_and_the_person_then_sees_the_doctor(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        add_doctor(c, env)
        add_doctor(c, env, DOCTOR2)
        c.post("/api/auth/login", json={"email": DOCTOR2["email"], "password": DOCTOR2["password"]})
        assert c.post(f"/api/doctor/offers/{case_id}/accept").json()["state"] == "accepted"
        c.post("/api/auth/login", json={"email": dd.DOCTOR["email"], "password": dd.DOCTOR["password"]})
        assert c.post(f"/api/doctor/offers/{case_id}/accept").status_code == 409          # too late
        assert c.get("/api/doctor/offers").json() == []                                    # no longer open
        assert c.get("/api/doctor/cases").json() == []                                     # not theirs
        login(c, dd.NORMAL.signup)
        cur = c.get("/api/consults/current").json()
        assert cur["state"] == "accepted" and cur["doctor_name"] == DOCTOR2["full_name"] and cur["status_text"] == consult.STATUS_ACCEPTED


def test_declining_hides_the_request_from_that_doctor_only(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        add_doctor(c, env)
        add_doctor(c, env, DOCTOR2)
        c.post("/api/auth/login", json={"email": DOCTOR2["email"], "password": DOCTOR2["password"]})
        assert c.post(f"/api/doctor/offers/{case_id}/decline").status_code == 204
        assert c.get("/api/doctor/offers").json() == []
        c.post("/api/auth/login", json={"email": dd.DOCTOR["email"], "password": dd.DOCTOR["password"]})
        assert len(c.get("/api/doctor/offers").json()) == 1


def test_cancelling_closes_it_and_a_doctor_can_no_longer_accept(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case = ask(c).json()
        assert c.post(f"/api/consults/{case['id']}/cancel").json()["state"] == "cancelled"
        assert c.get("/api/consults/current").json() is None
        add_doctor(c, env)
        c.post("/api/auth/login", json={"email": dd.DOCTOR["email"], "password": dd.DOCTOR["password"]})
        assert c.post(f"/api/doctor/offers/{case['id']}/accept").status_code == 409


def test_nobody_can_cancel_or_see_another_persons_request(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        c.post("/api/auth/logout")
        signup(c, dd.HIGH.signup, dd.HIGH.answers)
        assert c.get("/api/consults/current").json() is None
        assert c.post(f"/api/consults/{case_id}/cancel").status_code == 404
    with env() as s:
        assert s.get(ConsultCase, case_id).state == "open"


def test_doctors_and_reviewers_cannot_ask_for_a_doctor_and_patients_cannot_use_doctor_routes(env):
    with TestClient(app) as c:
        add_doctor(c, env)
        c.post("/api/auth/login", json={"email": dd.DOCTOR["email"], "password": dd.DOCTOR["password"]})
        assert ask(c).status_code == 403
        c.post("/api/auth/logout")
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert c.get("/api/doctor/offers").status_code == 403
        assert c.post("/api/doctor/offers/1/accept").status_code == 403



def test_after_accepting_the_doctor_gets_the_messages_and_the_summary(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, SELF_HARM)
        case_id = ask(c).json()["id"]
        add_doctor(c, env)
        c.post("/api/auth/logout")
        c.post("/api/auth/login", json={"email": dd.DOCTOR["email"], "password": dd.DOCTOR["password"]})
        assert c.post(f"/api/doctor/offers/{case_id}/accept").status_code == 200
        mine = c.get("/api/doctor/cases").json()[0]
        assert mine["case_id"] == case_id and mine["urgent"] is True and mine["reason"] == "urgent_message"
        summary = c.get(f"/api/doctor/cases/{case_id}/summary").json()
        assert [m["text"] for m in summary["recent_messages"]] == [SELF_HARM] and summary["checkin"]["phq9"] is not None
