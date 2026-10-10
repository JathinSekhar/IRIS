"""The optional AI conversational reply is fenced in: off by default, only for ordinary messages, output scanned, any failure falls back to fixed wording.

The real model is never called here: `companion.reply` is replaced by a fake, and the output checks are tested directly."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import companion
from devtools import demo_data as dd
from tests.test_messages import CALM, REVIEW_LEVEL, SELF_HARM, env, send, signup  # noqa: F401

LINE = "That sounds like a lot of pressure with exams so close. What part of it feels heaviest right now?"


@pytest.fixture()
def on(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")
    calls: list[tuple] = []

    def fake(text, history):
        calls.append((text, list(history)))
        return LINE

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
    assert companion.reply("hello", []) is None


def test_the_key_is_not_in_the_repo_files():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for path in list((root / "backend" / "app").rglob("*.py")) + list((root / "frontend" / "src").rglob("*.ts*")):
        assert "gsk_" not in path.read_text(encoding="utf-8", errors="ignore"), path
