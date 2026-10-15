"""Step 7: nobody accepts. After the team's goal (a goal, never a promise to the person) the person is told plainly, with the helplines,
and the reviewer and doctors see the request is overdue. Nothing the person reads mentions a time."""
import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models import ConsultCase
from app.services import consult
from devtools import demo_data as dd
from tests.test_consult import add_doctor, ask
from tests.test_consult_chat import doctor_login
from tests.test_messages import SELF_HARM, env, login, make_reviewer, send, signup  # noqa: F401


def age_case(env, case_id, minutes):
    with env() as s:
        s.get(ConsultCase, case_id).created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        s.commit()


def test_a_fresh_request_is_not_overdue(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        cur = ask(c).json()
        assert cur["waiting_long"] is False and cur["status_text"] != consult.STATUS_WAITING_LONG


def test_after_the_goal_the_person_is_told_plainly_and_keeps_the_helplines(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        age_case(env, case_id, settings.doctor_wait_goal_minutes + 1)
        cur = c.get("/api/consults/current").json()
        assert cur["waiting_long"] is True and cur["status_text"] == consult.STATUS_WAITING_LONG and cur["helplines"]
        assert cur["state"] == "open"                                          # still open: a doctor can still accept it


def test_the_overdue_line_never_promises_or_mentions_a_time():
    line = consult.STATUS_WAITING_LONG
    assert not re.search(r"\b(?:will (?:be|call|come|join|reach)|soon|shortly|minutes?|hours?|within|promise|guarantee)\b", line, re.IGNORECASE)
    assert "cannot say" in line and "numbers below" in line and "cancel" in line


def test_reviewer_and_doctors_see_overdue_requests(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, SELF_HARM)
        case_id = ask(c).json()["id"]
        age_case(env, case_id, settings.doctor_wait_goal_minutes + 3)
        make_reviewer(c, env)
        a = c.get("/api/reviewer/alerts").json()
        assert a["doctor_requests_overdue"] == 1 and a["doctor_requests_waiting"] == 1
        add_doctor(c, env)
        doctor_login(c)
        o = c.get("/api/doctor/offers").json()[0]
        assert o["overdue"] is True and o["waiting_minutes"] >= settings.doctor_wait_goal_minutes + 3


def test_once_accepted_it_is_no_longer_overdue(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        age_case(env, case_id, settings.doctor_wait_goal_minutes + 10)
        add_doctor(c, env)
        doctor_login(c)
        c.post(f"/api/doctor/offers/{case_id}/accept")
        login(c, dd.NORMAL.signup)
        cur = c.get("/api/consults/current").json()
        assert cur["waiting_long"] is False and cur["status_text"] == consult.STATUS_ACCEPTED
