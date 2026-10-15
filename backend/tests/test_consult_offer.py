"""Step 6: IRIS offers a doctor when it sees risk. The person always chooses; nothing is shared until they say yes; no line promises a doctor or a time.

Triggers: an explicit (urgent) message in the chat, a High check-in, or a reviewer's suggestion. Softer worrying language does not trigger it."""
import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, ConsultCase, DoctorOffer
from app.services import consult
from devtools import demo_data as dd
from tests.test_consult import add_doctor
from tests.test_consult_chat import accepted_case, doctor_login
from tests.test_messages import CALM, SELF_HARM, env, login, make_reviewer, send, signup  # noqa: F401


def offer(c):
    return c.get("/api/consults/offer").json()


def test_an_explicit_message_offers_a_doctor_and_shares_nothing_yet(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert offer(c) is None
        send(c, SELF_HARM)
        o = offer(c)
        assert o["reason"] == "urgent_message" and o["title"].startswith("Would you like to talk to a doctor")
        assert c.get("/api/consults/current").json() is None                  # no case exists until they say yes
    with env() as s:
        assert s.scalars(select(ConsultCase)).all() == []


def test_softer_worrying_language_does_not_trigger_an_offer(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        for text in (CALM, "I feel like a burden to everyone", "I hate my life"):
            send(c, text)
        assert offer(c) is None


def test_a_high_check_in_offers_a_doctor(env):
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json=dd.HIGH.signup)
        assert r.status_code == 201
        c.post("/api/consent", json={"version": "2026-10"})
        out = c.post("/api/checkin", json={"answers": dd.HIGH.answers}).json()
        assert out["offer_doctor"] is True and out["show_crisis_resources"] is True
        assert offer(c)["reason"] == "high_checkin"


def test_a_low_check_in_does_not_offer_a_doctor(env):
    with TestClient(app) as c:
        c.post("/api/auth/register", json=dd.NORMAL.signup)
        c.post("/api/consent", json={"version": "2026-10"})
        assert c.post("/api/checkin", json={"answers": dd.NORMAL.answers}).json()["offer_doctor"] is False
        assert offer(c) is None


def test_saying_yes_creates_an_urgent_request_that_doctors_see_first(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, CALM)
        calm_case = c.post("/api/consults", json={"share": True}).json()["id"]           # a calm request first
        c.post(f"/api/consults/{calm_case}/cancel")
        send(c, SELF_HARM)
        o = offer(c)
        r = c.post("/api/consults", json={"share": True, "offer_id": o["id"]})
        assert r.status_code == 201
        case_id = r.json()["id"]
        assert offer(c) is None                                                           # answered: the offer is gone
        add_doctor(c, env)
        doctor_login(c)
        first = c.get("/api/doctor/offers").json()[0]
        assert first["case_id"] == case_id and first["urgent"] is True and first["reason"] == "urgent_message"
    with env() as s:
        case = s.get(ConsultCase, case_id)
        assert case.source == "system" and case.urgent is True
        assert s.scalars(select(DoctorOffer)).one().resolution == "accepted"


def test_not_now_dismisses_without_sharing_and_a_later_urgent_message_offers_again(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, SELF_HARM)
        o = offer(c)
        assert c.post(f"/api/consults/offer/{o['id']}/dismiss").status_code == 204
        assert offer(c) is None and c.get("/api/consults/current").json() is None
        send(c, "I'm going to take all my pills")
        assert offer(c)["id"] != o["id"]
    with env() as s:
        assert "dismiss_doctor_offer" in [a.action for a in s.scalars(select(AuditLog))]


def test_no_offer_while_the_person_already_has_a_live_request(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        c.post("/api/consults", json={"share": True})
        send(c, SELF_HARM)
        assert offer(c) is None


def test_a_request_made_without_an_offer_is_still_marked_urgent_after_an_explicit_message(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, SELF_HARM)
        case_id = c.post("/api/consults", json={"share": True}).json()["id"]          # used the header link instead of the offer
        assert offer(c) is None
    with env() as s:
        case = s.get(ConsultCase, case_id)
        assert case.urgent is True and case.reason == "urgent_message" and case.source == "user"


def test_nobody_can_use_or_dismiss_another_persons_offer(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, SELF_HARM)
        o = offer(c)
        c.post("/api/auth/logout")
        signup(c, dd.HIGH.signup)
        assert c.post(f"/api/consults/offer/{o['id']}/dismiss").status_code == 404
        theirs = c.post("/api/consults", json={"share": True, "offer_id": o["id"]}).json()
    with env() as s:
        assert s.get(ConsultCase, theirs["id"]).source == "user"                      # someone else's offer is ignored, not used
        assert s.get(DoctorOffer, o["id"]).resolved_at is None


def test_a_reviewer_can_offer_a_doctor_and_the_person_decides(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        msg = send(c, "I feel like a burden to everyone")
        assert offer(c) is None
        make_reviewer(c, env)
        r = c.post(f"/api/reviewer/messages/{msg['id']}/offer-doctor")
        assert r.status_code == 200 and r.json()["offered"] is True
        login(c, dd.NORMAL.signup)
        o = offer(c)
        assert o["reason"] == "reviewer" and "your choice" in o["body"]
        case_id = c.post("/api/consults", json={"share": True, "offer_id": o["id"]}).json()["id"]
    with env() as s:
        case = s.get(ConsultCase, case_id)
        assert case.source == "reviewer" and case.urgent is False and case.reason == "reviewer"
        assert "offer_doctor_reviewer" in [a.action for a in s.scalars(select(AuditLog))]


def test_a_reviewer_cannot_offer_when_a_request_is_already_live_and_a_patient_cannot_offer(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        msg = send(c, CALM)
        assert c.post(f"/api/reviewer/messages/{msg['id']}/offer-doctor").status_code == 403
        c.post("/api/consults", json={"share": True})
        make_reviewer(c, env)
        assert c.post(f"/api/reviewer/messages/{msg['id']}/offer-doctor").status_code == 409


def test_the_reviewer_alert_counts_urgent_doctor_requests_nobody_has_accepted(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, SELF_HARM)
        c.post("/api/consults", json={"share": True, "offer_id": offer(c)["id"]})
        make_reviewer(c, env)
        assert c.get("/api/reviewer/alerts").json()["doctor_requests_waiting"] == 1


def test_an_explicit_line_in_the_doctor_chat_is_marked_urgent_not_just_worrying(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        login(c, dd.NORMAL.signup)
        c.post(f"/api/consults/{case_id}/messages", json={"text": "I feel like a burden"})
        c.post(f"/api/consults/{case_id}/messages", json={"text": "I am going to kill myself tonight"})
        c.post(f"/api/consults/{case_id}/messages", json={"text": "thank you for listening"})
        assert all(m["flag"] is None for m in c.get(f"/api/consults/{case_id}/messages").json())     # the person never sees flags
        doctor_login(c)
        assert [m["flag"] for m in c.get(f"/api/doctor/cases/{case_id}/messages").json()] == ["worrying", "urgent", None]


def test_the_offer_lines_never_promise_a_doctor_or_a_time():
    banned = r"\b(?:will (?:be|call|come|join|reach|contact)|is coming|on (?:the|their) way|soon|shortly|minutes?|hours?|within|promise|guarantee)\b"
    for title, body in consult.OFFER_TEXT.values():
        assert not re.search(banned, f"{title} {body}", re.IGNORECASE), title
        assert "straight away" in body                                       # every offer says it may not be immediate
