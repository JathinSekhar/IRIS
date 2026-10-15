"""The written summary in the doctor's case list: built by rules from the profile, the check-in answers and the chat. Never from a model."""
from fastapi.testclient import TestClient

from app.main import app
from devtools import demo_data as dd
from tests.test_consult import add_doctor
from tests.test_consult_chat import doctor_login
from tests.test_messages import CALM, SELF_HARM, env, send, signup  # noqa: F401


def _narrative(c, env, person, answers, messages):
    signup(c, person, answers)
    for m in messages:
        send(c, m)
    case_id = c.post("/api/consults", json={"share": True}).json()["id"]
    add_doctor(c, env)
    doctor_login(c)
    c.post(f"/api/doctor/offers/{case_id}/accept")
    return c.get(f"/api/doctor/cases/{case_id}/summary").json()["narrative"]


def test_a_high_risk_person_is_described_from_their_check_in_and_chat(env):
    with TestClient(app) as c:
        text = _narrative(c, env, dd.HIGH.signup, dd.HIGH.answers, [SELF_HARM])
    print(text)
    assert text.startswith("Arjun (")
    assert "severe low mood" in text and "severe anxiety" in text and "high flag" in text
    assert "In their own words" in text and "1 message" in text and "worrying language (1 explicit)" in text


def test_a_low_risk_person_is_described_without_alarm(env):
    with TestClient(app) as c:
        text = _narrative(c, env, dd.NORMAL.signup, dd.NORMAL.answers, [CALM])
    print(text)
    assert "minimal low mood" in text and "flag" not in text and "worrying" not in text
    assert "study or exam pressure" in text


def test_someone_who_has_not_written_yet(env):
    with TestClient(app) as c:
        text = _narrative(c, env, dd.NORMAL.signup, dd.NORMAL.answers, [])
    assert text.endswith("They have not written to IRIS yet.")
