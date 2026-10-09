"""The chat and its human review queue. These tests pin down the safety design: nothing is ever cleared automatically, every message waits for a
person, safety layers override a calm message, reviewers can only raise priority, reviewer access is audited, and the person sees no scores or labels."""
import json
import os

os.environ.setdefault("IRIS_DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_service import get_auth_service
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import AuditLog, Message, Prediction, Review, User
from devtools import demo_data as dd
from devtools.fake_auth import FakeAuth

CALM = "I have exams next week and I am struggling to study"
SELF_HARM = "I am going to kill myself tonight"
REVIEW_LEVEL = "Nobody would notice if I was gone"          # review level: helplines and priority Medium, but not the urgent response


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fake = FakeAuth()

    def _db():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_auth_service] = lambda: fake
    yield factory
    app.dependency_overrides.clear()


def signup(c, data, checkin=None):
    r = c.post("/api/auth/register", json=data)
    assert r.status_code == 201, r.text
    assert c.post("/api/consent", json={"version": settings.consent_version}).status_code == 200
    if checkin:
        assert c.post("/api/checkin", json={"answers": checkin}).status_code == 201


def login(c, data):
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"email": data["email"], "password": data["password"]}).status_code == 200


def make_reviewer(c, env):
    c.post("/api/auth/logout")
    assert c.post("/api/auth/register", json=dd.REVIEWER).status_code == 201
    with env() as s:
        s.scalar(select(User).where(User.email == dd.REVIEWER["email"])).role = "reviewer"
        s.commit()


def send(c, text):
    r = c.post("/api/messages", json={"text": text})
    assert r.status_code == 201, r.text
    return r.json()


def prediction(env, message_id):
    with env() as s:
        return s.scalar(select(Prediction).where(Prediction.message_id == message_id))


# --- what the person sees ------------------------------------------------------------------------------------------------------------------------

LABELS = ["risk", "urgent", "urgency", "priority", "score", "low", "medium", "high", "safe"]


def test_the_reply_is_supportive_and_shows_no_scores_labels_or_claims_of_safety(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        body = send(c, CALM)
        assert set(body) == {"id", "text", "created_at", "reply", "care_status", "status_text"}
        assert set(body["reply"]) == {"layout", "helplines", "intro", "listening", "self_help", "reach_out", "crisis_lead", "crisis_lines",
                                      "show_crisis_resources", "emergency_footer", "closing", "a_person_may_reach_out"}
        assert body["care_status"] == "waiting" and body["reply"]["layout"] == "tips" and body["reply"]["helplines"] == []
        shown = json.dumps(body["reply"]).lower()
        for word in LABELS:
            assert f" {word} " not in f" {shown.replace(chr(34), ' ').replace(',', ' ').replace('.', ' ')} ", word
        assert body["reply"]["self_help"] and body["reply"]["reach_out"]
        assert "IRIS is not an emergency service" in body["reply"]["emergency_footer"]            # always visible
        assert body["reply"]["show_crisis_resources"] is False and body["reply"]["a_person_may_reach_out"] is True


def test_explicit_self_harm_gets_helplines_and_no_self_help_whatever_the_check_in_said(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)               # a calm baseline must not matter
        body = send(c, SELF_HARM)
        r = body["reply"]
        assert r["show_crisis_resources"] and r["crisis_lines"] and r["crisis_lead"] and not r["self_help"]
        assert any("112" in line for line in r["crisis_lines"])
    p = prediction(env, body["id"])
    assert p.urgency == "high" and p.rule_level == "high" and p.status == "pending_human_review" and p.needs_human


def test_a_high_check_in_floor_raises_a_calm_message(env):
    with TestClient(app) as c:
        signup(c, dd.HIGH.signup, dd.HIGH.answers)
        body = send(c, CALM)
        assert body["reply"]["show_crisis_resources"] is True
    p = prediction(env, body["id"])
    assert p.baseline_floor == "high" and p.baseline_known and p.urgency == "high"
    assert any("baseline floor" in r for r in p.reasons)


def test_a_calm_message_is_low_but_still_waits_for_a_person_and_no_model_is_used(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        body = send(c, CALM)
    p = prediction(env, body["id"])
    assert p.urgency == "low" and p.status == "pending_human_review" and p.needs_human and p.route == "human_reviewer"
    assert p.probabilities is None and p.model_urgency is None and p.model_version.startswith("none")
    assert "NOT ZERO RISK" in p.reviewer_note and p.reply == body["reply"]                          # what was shown is what is stored


def test_no_check_in_means_the_baseline_is_unknown_not_safe(env):
    with TestClient(app) as c:
        signup(c, dd.MEDIUM.signup)
        body = send(c, CALM)
    p = prediction(env, body["id"])
    assert p.baseline_known is False and p.baseline_floor == "none" and p.checkin_id is None


@pytest.mark.parametrize("text", [CALM, SELF_HARM, REVIEW_LEVEL, "ok", "नमस्ते मैं ठीक नहीं हूँ", "How do I book a counsellor appointment?", "x" * 4000])
def test_every_message_waits_for_a_person_nothing_is_cleared(text, env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        body = send(c, text)
    p = prediction(env, body["id"])
    assert p.status == "pending_human_review" and p.needs_human and p.route == "human_reviewer"
    with env() as s:
        assert s.scalar(select(Review).where(Review.message_id == body["id"])) is None            # nobody has reviewed it, so it is not closed


# --- who can do what -------------------------------------------------------------------------------------------------------------------------------

def test_sign_in_consent_and_input_checks(env):
    with TestClient(app) as c:
        assert c.post("/api/messages", json={"text": "hi"}).status_code == 401
        assert c.get("/api/messages").status_code == 401
        c.post("/api/auth/register", json=dd.NORMAL.signup)                                          # signed in but NOT consented
        assert c.post("/api/messages", json={"text": "hello there"}).status_code == 403
        assert c.post("/api/consent", json={"version": settings.consent_version}).status_code == 200
        assert c.post("/api/messages", json={"text": "   "}).status_code == 422
        assert c.post("/api/messages", json={"text": ""}).status_code == 422
        assert c.post("/api/messages", json={"text": "a" * 5001}).status_code == 422
        assert c.post("/api/messages", json={"text": "hello there"}).status_code == 201


def test_rate_limit(env, monkeypatch):
    monkeypatch.setattr(settings, "message_rate_limit_per_minute", 3)
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup)
        for _ in range(3):
            send(c, CALM)
        assert c.post("/api/messages", json={"text": CALM}).status_code == 429


def test_a_person_only_ever_sees_their_own_conversation(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup)
        mine = send(c, "My own private message about exams")
        login(c, dd.NORMAL.signup)
        assert [m["id"] for m in c.get("/api/messages").json()] == [mine["id"]]
        c.post("/api/auth/logout")
        signup(c, dd.MEDIUM.signup)
        assert c.get("/api/messages").json() == []
        send(c, "A different person writing")
        assert len(c.get("/api/messages").json()) == 1


def test_people_cannot_reach_any_reviewer_message_endpoint(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup)
        m = send(c, CALM)
        for call in (lambda: c.get("/api/reviewer/messages"), lambda: c.get(f"/api/reviewer/messages/{m['id']}"),
                     lambda: c.post(f"/api/reviewer/messages/{m['id']}/escalate", json={"to": "high", "reason": "trying"}),
                     lambda: c.post(f"/api/reviewer/messages/{m['id']}/review", json={"urgency": "low", "notes": "clear it"})):
            assert call().status_code == 403
    assert prediction(env, m["id"]).status == "pending_human_review" and prediction(env, m["id"]).urgency == "low"


# --- the reviewer's queue --------------------------------------------------------------------------------------------------------------------------

def _three_messages(c, env):
    signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
    low = send(c, CALM)
    review = send(c, REVIEW_LEVEL)
    high = send(c, SELF_HARM)
    return low, review, high


def test_the_queue_orders_by_priority_and_never_shows_message_text(env):
    with TestClient(app) as c:
        low, review, high = _three_messages(c, env)
        make_reviewer(c, env)
        q = c.get("/api/reviewer/messages").json()
        assert [x["id"] for x in q] == [high["id"], review["id"], low["id"]]
        assert [x["priority"] for x in q] == ["high", "medium", "low"]
        assert all("text" not in x for x in q) and q[0]["rule_flagged"] and not q[2]["rule_flagged"]
        assert all(x["status"] == "pending_human_review" for x in q)


def test_opening_a_message_is_audited_and_shows_why(env):
    with TestClient(app) as c:
        low, review, high = _three_messages(c, env)
        make_reviewer(c, env)
        d = c.get(f"/api/reviewer/messages/{high['id']}").json()
        assert d["text"] == SELF_HARM and d["priority"] == "high" and d["rule_level"] == "high" and d["rule_hits"]
        assert "URGENT" in d["reviewer_note"] and d["model_version"].startswith("none") and d["reply_shown"]["crisis_lines"]
        assert c.get("/api/reviewer/messages/99999").status_code == 404
    with env() as s:
        actions = [a.action for a in s.scalars(select(AuditLog).order_by(AuditLog.id))]
        assert "view_message" in actions


def test_listing_the_queue_is_audited(env):
    with TestClient(app) as c:
        _three_messages(c, env)
        make_reviewer(c, env)
        c.get("/api/reviewer/messages")
    with env() as s:
        assert "list_message_queue" in [a.action for a in s.scalars(select(AuditLog))]


def test_a_reviewer_can_raise_a_low_case_with_a_reason_and_it_moves_up(env):
    with TestClient(app) as c:
        low, review, high = _three_messages(c, env)
        make_reviewer(c, env)
        d = c.post(f"/api/reviewer/messages/{low['id']}/escalate", json={"to": "medium", "reason": "second paragraph mentions giving things away"}).json()
        assert d["priority"] == "medium" and d["initial_priority"] == "low" and d["status"] == "pending_human_review"
        assert any("escalated by a reviewer to medium" in r for r in d["reasons"]) and d["history"][-1]["kind"] == "escalation"
        d = c.post(f"/api/reviewer/messages/{low['id']}/escalate", json={"to": "high", "reason": "contradicts what they said earlier"}).json()
        assert d["priority"] == "high" and "URGENT" in d["reviewer_note"] and len(d["history"]) == 2
        q = c.get("/api/reviewer/messages").json()
        assert q[0]["priority"] == "high" and next(x for x in q if x["id"] == low["id"])["reviewer_raised"] is True
    with env() as s:
        assert "escalate_message" in [a.action for a in s.scalars(select(AuditLog))]


def test_escalation_only_raises_and_needs_a_reason(env):
    with TestClient(app) as c:
        low, review, high = _three_messages(c, env)
        make_reviewer(c, env)
        url = f"/api/reviewer/messages/{high['id']}/escalate"
        assert c.post(url, json={"to": "medium", "reason": "downgrade attempt"}).status_code == 422       # cannot lower High
        assert c.post(url, json={"to": "low", "reason": "downgrade attempt"}).status_code == 422          # 'low' is not an escalation
        ok = f"/api/reviewer/messages/{low['id']}/escalate"
        assert c.post(ok, json={"to": "high", "reason": "  "}).status_code == 422
        assert c.post(ok, json={"to": "high", "reason": "ab"}).status_code == 422
        assert c.get(f"/api/reviewer/messages/{high['id']}").json()["priority"] == "high"


def test_only_a_reviewers_own_judgement_moves_a_case_out_of_pending(env):
    with TestClient(app) as c:
        low, review, high = _three_messages(c, env)
        make_reviewer(c, env)
        before = c.get("/api/reviewer/messages").json()
        assert all(x["status"] == "pending_human_review" for x in before)
        d = c.post(f"/api/reviewer/messages/{low['id']}/review", json={"urgency": "low", "notes": "Read in full. Ordinary exam stress; no warning signs."}).json()
        assert d["status"] == "reviewed" and d["history"][-1]["kind"] == "judgement" and d["initial_priority"] == "low"
        assert c.post(f"/api/reviewer/messages/{low['id']}/review", json={"urgency": "low", "notes": ""}).status_code == 409        # not twice
        assert c.post(f"/api/reviewer/messages/{low['id']}/escalate", json={"to": "high", "reason": "too late"}).status_code == 409
        q = c.get("/api/reviewer/messages").json()
        assert [x["status"] for x in q] == ["pending_human_review", "pending_human_review", "reviewed"]        # reviewed cases drop to the bottom
    with env() as s:
        assert "review_message" in [a.action for a in s.scalars(select(AuditLog))]


def test_the_stored_prediction_is_never_overwritten_by_review_actions(env):
    with TestClient(app) as c:
        low, review, high = _three_messages(c, env)
        make_reviewer(c, env)
        c.post(f"/api/reviewer/messages/{low['id']}/escalate", json={"to": "high", "reason": "warning signs"})
        c.post(f"/api/reviewer/messages/{low['id']}/review", json={"urgency": "medium", "notes": "handled"})
    p = prediction(env, low["id"])
    assert p.initial_urgency == "low" and p.model_version.startswith("none") and p.reply == low["reply"]


def test_deleting_a_person_removes_their_messages_predictions_and_reviews(env):
    from sqlalchemy import delete, func, text
    with TestClient(app) as c:
        low, *_ = _three_messages(c, env)
        make_reviewer(c, env)
        c.post(f"/api/reviewer/messages/{low['id']}/escalate", json={"to": "medium", "reason": "check"})
    with env() as s:
        s.execute(text("PRAGMA foreign_keys=ON"))                       # SQLite enforces foreign keys only when asked; Postgres always does
        before = [s.scalar(select(func.count()).select_from(t)) for t in (Message, Prediction, Review)]
        assert before == [3, 3, 1]
        s.execute(delete(User).where(User.email == dd.NORMAL.signup["email"]))
        s.commit()
        assert [s.scalar(select(func.count()).select_from(t)) for t in (Message, Prediction, Review)] == [0, 0, 0]


def test_concerning_language_gets_support_and_helplines_but_no_self_help_tips(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        r = send(c, "Nobody would notice if I was gone")["reply"]
        assert r["show_crisis_resources"] and r["crisis_lines"] and not r["self_help"] and r["reach_out"]
        calm = send(c, CALM)["reply"]
        assert calm["self_help"] and not calm["show_crisis_resources"]               # ordinary messages keep their advice



# --- good news, urgent replies, live status and instant alerts -----------------------------------------------------------------------------------------------

def test_good_news_gets_a_warm_reply_with_no_advice_and_still_waits_for_a_person(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        for text in ["I had a great day at college today and enjoyed spending time with my friends.", "My exams went really well, and I am proud of how much I studied.",
                     "I used to feel anxious about college, but now I am doing much better."]:
            body = send(c, text)
            r = body["reply"]
            assert r["layout"] == "celebrate" and not r["self_help"] and not r["show_crisis_resources"] and r["helplines"] == []
            p = prediction(env, body["id"])
            assert p.status == "pending_human_review" and p.needs_human and p.urgency == "low"


def test_mixed_messages_are_never_cheerful(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        for text in ["I passed my exam but I feel worthless", "I am so happy but sometimes I want to die", "I feel happy and nobody would notice if I disappeared"]:
            assert send(c, text)["reply"]["layout"] != "celebrate", text


def test_explicit_statements_about_ending_ones_life_are_urgent_with_tap_to_call_helplines_and_an_honest_status(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        body = send(c, "I have been thinking about ending my life, and I don't know what to do")
        r = body["reply"]
        assert r["layout"] == "help_now" and not r["self_help"] and r["show_crisis_resources"]
        assert [h["number"] for h in r["helplines"]] == ["14416", "1800-599-0019", "112"] and [h["tel"] for h in r["helplines"]] == ["14416", "18005990019", "112"]
        text = body["status_text"].lower()
        assert "alerted" in text and "cannot say exactly when" in text            # honest: no time, no doctor
        assert "minute" not in text and "doctor" not in text and "connect" not in text
    p = prediction(env, body["id"])
    assert p.urgency == "high" and p.initial_urgency == "high" and p.status == "pending_human_review"


def test_the_person_sees_the_truth_about_whether_a_person_has_opened_their_message(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, SELF_HARM)
        assert m["care_status"] == "waiting"
        make_reviewer(c, env)
        c.get(f"/api/reviewer/messages/{m['id']}")                                  # a reviewer opens it
        login(c, dd.NORMAL.signup)
        mine = c.get("/api/messages").json()[0]
        assert mine["care_status"] == "being_read" and "reading your message now" in mine["status_text"]
        login(c, dd.REVIEWER)
        c.post(f"/api/reviewer/messages/{m['id']}/review", json={"urgency": "high", "notes": "contacted"})
        login(c, dd.NORMAL.signup)
        mine = c.get("/api/messages").json()[0]
        assert mine["care_status"] == "reviewed" and "has read your message" in mine["status_text"]


def test_a_calm_message_status_never_sounds_urgent_and_promises_no_time(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        b = send(c, CALM)
        assert b["status_text"] == "A person on our team will read this, which may take some time." and "alerted" not in b["status_text"]


def test_reviewers_get_instant_counts_only_alerts_that_are_not_audited_and_closed_cases_clear_them(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, CALM)
        urgent = send(c, SELF_HARM)
        make_reviewer(c, env)
        a = c.get("/api/reviewer/alerts").json()
        assert set(a) == {"urgent_waiting", "urgent_unopened", "oldest_unopened_seconds", "latest_urgent_id"}
        assert a["urgent_waiting"] == 1 and a["urgent_unopened"] == 1 and a["latest_urgent_id"] == urgent["id"] and a["oldest_unopened_seconds"] >= 0
        with env() as s:
            before = len(s.scalars(select(AuditLog)).all())
        for _ in range(5):
            c.get("/api/reviewer/alerts")
        with env() as s:
            assert len(s.scalars(select(AuditLog)).all()) == before                 # polling writes nothing: it exposes no content
        c.get(f"/api/reviewer/messages/{urgent['id']}")                              # opening it stops it being "unopened"
        a = c.get("/api/reviewer/alerts").json()
        assert a["urgent_waiting"] == 1 and a["urgent_unopened"] == 0 and a["oldest_unopened_seconds"] is None
        c.post(f"/api/reviewer/messages/{urgent['id']}/review", json={"urgency": "high", "notes": "handled"})
        assert c.get("/api/reviewer/alerts").json()["urgent_waiting"] == 0


def test_a_reviewer_raising_a_case_to_high_puts_it_in_the_alerts(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        low = send(c, CALM)
        make_reviewer(c, env)
        assert c.get("/api/reviewer/alerts").json()["urgent_waiting"] == 0
        c.post(f"/api/reviewer/messages/{low['id']}/escalate", json={"to": "high", "reason": "warning signs"})
        assert c.get("/api/reviewer/alerts").json()["urgent_waiting"] == 1


def test_people_cannot_read_the_alerts(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup)
        assert c.get("/api/reviewer/alerts").status_code == 403


def test_the_chat_page_uses_exactly_the_reviewed_emergency_sentence():
    from pathlib import Path
    from app.services import triage
    page = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "Chat.tsx").read_text(encoding="utf-8")
    assert triage.support.EMERGENCY_FOOTER in page


def test_the_chat_has_no_toolkit_and_uses_no_emoji():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "frontend" / "src"
    page = (src / "pages" / "Chat.tsx").read_text(encoding="utf-8")
    assert "toolkit" not in page.lower() and "/api/toolkit" not in (src / "lib" / "api.ts").read_text(encoding="utf-8")
    emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2764]")
    assert not emoji.search(page), "no emoji in the chat"
