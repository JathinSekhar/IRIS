"""'Did this help?' on an ordinary reply. Stepped care: IRIS suggests steps first; 'Not really' offers a doctor (the person still chooses).
Worrying or urgent messages are never asked to be rated: they already get helplines and a doctor offer directly."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import ConsultCase, DoctorOffer
from app.services import consult
from devtools import demo_data as dd
from tests.test_consult import add_doctor
from tests.test_consult_chat import doctor_login
from tests.test_messages import CALM, SELF_HARM, env, send, signup  # noqa: F401


def rate(c, message_id, helpful):
    return c.post(f"/api/messages/{message_id}/feedback", json={"helpful": helpful})


def test_an_ordinary_reply_can_be_rated_and_worrying_or_urgent_ones_cannot(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        calm = send(c, CALM)
        assert calm["can_rate"] is True and calm["helpful"] is None
        for text in ("I feel like a burden to everyone", SELF_HARM, "hi"):
            m = send(c, text)
            assert m["can_rate"] is False, text
            assert rate(c, m["id"], False).status_code == 409


def test_yes_is_recorded_and_offers_nothing(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, CALM)
        out = rate(c, m["id"], True).json()
        assert out["helpful"] is True
        assert c.get("/api/consults/offer").json() is None


def test_not_really_offers_a_doctor_and_saying_yes_creates_a_non_urgent_request(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, CALM)
        assert rate(c, m["id"], False).json()["helpful"] is False
        offer = c.get("/api/consults/offer").json()
        assert offer["reason"] == "self_help" and "straight away" in offer["body"]
        assert c.get("/api/consults/current").json() is None                  # still nothing shared
        case_id = c.post("/api/consults", json={"share": True, "offer_id": offer["id"]}).json()["id"]
        add_doctor(c, env)
        doctor_login(c)
        o = c.get("/api/doctor/offers").json()[0]
        assert o["case_id"] == case_id and o["urgent"] is False and o["reason"] == "self_help"
    with env() as s:
        case = s.get(ConsultCase, case_id)
        assert case.urgent is False and case.source == "system"
        assert s.scalars(select(DoctorOffer)).one().resolution == "accepted"


def test_only_the_owner_can_rate(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, CALM)
        c.post("/api/auth/logout")
        signup(c, dd.HIGH.signup)
        assert rate(c, m["id"], False).status_code == 404


def test_the_self_help_offer_text_makes_no_promise():
    import re
    title, body = consult.OFFER_TEXT["self_help"]
    assert not re.search(r"\b(?:will (?:be|call|come|join|reach)|soon|shortly|minutes?|hours?|within|promise|guarantee)\b", f"{title} {body}", re.I)


def test_a_person_with_a_high_check_in_is_never_asked_to_rate(env):
    with TestClient(app) as c:
        signup(c, dd.HIGH.signup, dd.HIGH.answers)
        m = send(c, CALM)
        assert m["reply"]["helplines"] and m["can_rate"] is False
