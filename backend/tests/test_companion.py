"""The optional AI conversational reply is fenced in: off by default, only for ordinary messages, output scanned, any failure falls back to fixed wording.

The real model is never called here: `companion.reply` is replaced by a fake, and the output checks are tested directly."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import companion
from devtools import demo_data as dd
from tests.test_messages import CALM, REVIEW_LEVEL, SELF_HARM, env, make_reviewer, send, signup  # noqa: F401

LINE = "That sounds like a lot of pressure with exams so close. What part of it feels heaviest right now?"


@pytest.fixture()
def on(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")
    calls: list[tuple] = []

    def fake(text, history):
        calls.append((text, list(history)))
        return LINE, False

    monkeypatch.setattr(companion, "reply", fake)
    return calls


def test_off_by_default_the_fixed_wording_is_used(env):
    assert settings.llm_enabled is False
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert send(c, CALM)["reply"]["companion"] is None


def test_an_ordinary_message_gets_the_conversational_line_and_keeps_the_review(env, on):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, CALM)
        assert m["reply"]["companion"] == LINE and m["care_status"] == "waiting"
        assert m["reply"]["intro"] and m["reply"]["emergency_footer"]       # the fixed wording is still stored beside it
    assert len(on) == 1


def test_earlier_turns_are_passed_as_history(env, on):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        send(c, CALM)
        send(c, "mostly the maths paper")
    assert on[1][1] == [(CALM, LINE)]


@pytest.mark.parametrize("text", [SELF_HARM, REVIEW_LEVEL, "I hate my life", "I'm thinking of killing myself"])
def test_worrying_messages_never_reach_the_model(env, on, text):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, text)
        assert m["reply"]["companion"] is None
        assert m["reply"]["helplines"]
    assert on == []


def test_a_high_check_in_floor_keeps_the_fixed_wording_even_for_a_calm_message(env, on):
    with TestClient(app) as c:
        signup(c, dd.HIGH.signup, dd.HIGH.answers)
        assert send(c, "yah i am feeling better")["reply"]["companion"] is None
    assert on == []


@pytest.mark.parametrize("bad", [
    "Everything will be fine, I promise.",
    "A doctor will call you soon.",
    "We will reach out within 10 minutes.",
    "That sounds like depression. How long?",
    "You are safe now, don't worry.",
    "Please call 112 if it gets worse.",
    "I am so sorry \U0001F614 what happened?",
    "I could kill myself too, honestly.",
    "x" * 500,
    "",
])
def test_unsafe_model_output_is_thrown_away(bad):
    assert companion.acceptable(bad) is None


def test_a_good_line_passes_and_is_tidied():
    assert companion.acceptable('  "' + LINE + '"  ') == LINE


def test_a_model_failure_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")

    def boom(*a, **k):
        raise TimeoutError("slow")

    monkeypatch.setattr(companion.httpx, "post", boom)
    assert companion.reply("hello", []) == (None, False)


# --- the guard: the model's own words about self-harm, death or pills mean the rules missed something -------------------------------------------

# Replies the model really wrote in the chat probe (2026-11-26) to messages the rule layer missed.
WORRIED = [
    "You’ve shared that you’re feeling overwhelmed enough to consider taking all the pills you have. What thoughts or feelings are coming up for you?",
    "You’ve shared that you’re feeling extremely exhausted and that you’ve even typed something suggesting you might harm yourself.",
    "It sounds like you’re feeling like you have no desire to keep going right now. What thoughts or feelings are coming up for you?",
    "It sounds like you have been thinking about death a lot lately. What has been on your mind?",
    "CONCERN",                                  # the model's own judgement (see SYSTEM_PROMPT)
    "concern.",
]
ORDINARY = [
    LINE,
    "Hi there! It’s nice to hear from you. What’s on your mind today?",
    "That’s wonderful to hear that your exams went so well! What do you think helped you feel confident today?",
    "It sounds like the tight finances and rent worries are weighing on you a lot right now. What’s been the most challenging part?",
    "That is an understandable concern before results day. What would help you feel a little more ready?",
    "It sounds like you’re feeling isolated and wish you had more connection with people at college. What would feel meaningful to you?",
]


@pytest.mark.parametrize("raw", WORRIED)
def test_the_guard_sees_worrying_model_words(raw):
    assert companion.concern(raw)


@pytest.mark.parametrize("raw", ORDINARY)
def test_the_guard_leaves_ordinary_replies_alone(raw):
    assert not companion.concern(raw)


class _Groq:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


def test_a_worrying_model_reply_is_never_shown_and_the_message_is_flagged(env, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")
    monkeypatch.setattr(companion.httpx, "post", lambda *a, **k: _Groq(WORRIED[2]))
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, "mujhe ab jeena nahi hai")                  # Hinglish: the rule layer misses it
        r = m["reply"]
        assert r["companion"] is None and "desire" not in str(r)
        assert r["helplines"] and r["layout"] == "support" and not m["can_rate"]
        make_reviewer(c, env)
        d = c.get(f"/api/reviewer/messages/{m['id']}").json()
        assert d["priority"] == "medium" and companion.GUARD_REASON in d["reasons"]
        assert d["rule_level"] == "none" and d["rule_hits"] == []          # the rules did not fire, and the record says so


def test_an_ordinary_model_reply_is_shown(env, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")
    monkeypatch.setattr(companion.httpx, "post", lambda *a, **k: _Groq(LINE))
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = send(c, "exams are stressing me out")
        assert m["reply"]["companion"] == LINE and not m["reply"]["helplines"]


def test_the_key_is_not_in_the_repo_files():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for path in list((root / "backend" / "app").rglob("*.py")) + list((root / "frontend" / "src").rglob("*.ts*")):
        assert "gsk_" not in path.read_text(encoding="utf-8", errors="ignore"), path
