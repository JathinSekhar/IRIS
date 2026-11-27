"""New chat and Past chats: messages carry their chat's id, history can be read one chat at a time, and the list shows only your own chats."""
from fastapi.testclient import TestClient

from app.main import app
from devtools import demo_data as dd
from tests.test_messages import env, signup  # noqa: F401

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


def say(c, text, chat=None):
    r = c.post("/api/messages", json={"text": text, **({"conversation_id": chat} if chat else {})})
    assert r.status_code == 201, r.text
    return r.json()


def test_messages_are_grouped_into_chats_and_listed_newest_first(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert say(c, "exams are stressing me out", A)["conversation_id"] == A
        say(c, "mostly the maths paper", A)
        say(c, "my exams went really well today!", B)
        chats = c.get("/api/messages/conversations").json()
        assert [ch["id"] for ch in chats] == [B, A]
        assert chats[1]["title"] == "exams are stressing me out" and chats[1]["count"] == 2
        assert [m["text"] for m in c.get(f"/api/messages?conversation={A}").json()] == ["exams are stressing me out", "mostly the maths paper"]
        assert len(c.get("/api/messages").json()) == 3                     # without a chat: everything, as before


def test_messages_from_before_chats_existed_form_one_earlier_chat(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        say(c, "an older message")
        chats = c.get("/api/messages/conversations").json()
        assert chats[0]["id"] == "earlier"
        assert [m["text"] for m in c.get("/api/messages?conversation=earlier").json()] == ["an older message"]


def test_a_long_first_message_gives_a_short_title(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        say(c, "word " * 40, A)
        title = c.get("/api/messages/conversations").json()[0]["title"]
        assert len(title) <= 61 and title.endswith("…")


def test_a_bad_chat_id_is_refused(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert c.post("/api/messages", json={"text": "hi", "conversation_id": "not-a-chat"}).status_code == 422
        assert c.get("/api/messages?conversation=../../etc").status_code == 422


def test_nobody_sees_anyone_elses_chats(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        say(c, "private words", A)
        c.post("/api/auth/logout")
        signup(c, dd.MEDIUM.signup, dd.MEDIUM.answers)
        assert c.get("/api/messages/conversations").json() == []
        assert c.get(f"/api/messages?conversation={A}").json() == []


def test_safety_still_applies_in_every_chat(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        m = say(c, "I want to die", B)
        assert m["reply"]["helplines"] and m["reply"]["layout"] == "help_now"
