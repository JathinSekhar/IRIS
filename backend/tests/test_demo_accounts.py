"""The demo accounts must do exactly what docs/DEMO_ACCOUNTS.md says. This submits their answers through the real API."""
import os
from pathlib import Path

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
from app.models import User
from app.services.questionnaire import clean_answers
from devtools import demo_data as dd
from devtools.fake_auth import FakeAuth

DOCS = Path(__file__).resolve().parents[2] / "docs" / "DEMO_ACCOUNTS.md"


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


def signup(c, signup_data):
    r = c.post("/api/auth/register", json=signup_data)
    assert r.status_code == 201, r.text
    assert c.post("/api/consent", json={"version": settings.consent_version}).status_code == 200


@pytest.mark.parametrize("user", dd.USERS, ids=lambda u: u.key)
def test_every_demo_answer_is_valid_and_none_is_silently_dropped(user):
    cleaned = clean_answers(user.answers)
    assert set(cleaned) == set(user.answers)                              # no answer belongs to a hidden question
    rows = dd.visible_answers(user)
    assert not any(r[2] == "(skip)" for r in rows)                        # the sheet answers every question that is asked


@pytest.mark.parametrize("user", dd.USERS, ids=lambda u: u.key)
def test_each_demo_user_produces_the_documented_outcome(user, env):
    with TestClient(app) as c:
        signup(c, user.signup)
        r = c.post("/api/checkin", json={"answers": user.answers})
        assert r.status_code == 201
        assert r.json()["show_crisis_resources"] is user.expected["show_crisis_resources"]
    with env() as s:
        row = s.scalar(select(User).where(User.email == user.signup["email"]))
        ci = row.checkins[0]
        assert ci.baseline_risk == user.expected["baseline_risk"] and ci.escalated is user.expected["escalated"]
        sc = ci.scores
        assert sc["phq9"]["score"] == user.expected["phq9"] and sc["phq9"]["band"] == user.expected["phq9_band"]
        assert sc["gad7"]["score"] == user.expected["gad7"] and sc["gad7"]["band"] == user.expected["gad7_band"]
        assert sc["safety"]["tier"] == user.expected["safety_tier"]
        assert sc["phq9"]["complete"] and sc["gad7"]["complete"]


def test_the_reviewer_queue_orders_the_three_users_as_documented(env):
    with TestClient(app) as c:
        for u in dd.USERS:
            signup(c, u.signup)
            assert c.post("/api/checkin", json={"answers": u.answers}).status_code == 201
            c.post("/api/auth/logout")
        assert c.post("/api/auth/register", json=dd.REVIEWER).status_code == 201
        with env() as s:
            rev = s.scalar(select(User).where(User.email == dd.REVIEWER["email"]))
            rev.role = "reviewer"
            s.commit()
        queue = c.get("/api/reviewer/checkins").json()
        names = [q["user_name"] for q in queue]
        by_position = sorted(dd.USERS, key=lambda u: u.expected["queue_position"])
        assert names == [u.signup["full_name"] for u in by_position]
        assert queue[0]["escalated"] is True and [q["baseline_risk"] for q in queue] == ["high", "medium", "low"]
        detail = c.get(f"/api/reviewer/checkins/{queue[0]['id']}").json()
        assert detail["emergency_contact"] == dd.HIGH.signup["emergency_contact"]
        assert detail["scores"]["safety"]["urgency_floor"] == "high"


def test_demo_users_can_log_in_again_and_wrong_passwords_are_refused(env):
    with TestClient(app) as c:
        for u in dd.USERS:
            signup(c, u.signup)
            c.post("/api/auth/logout")
            ok = c.post("/api/auth/login", json={"email": u.signup["email"], "password": u.signup["password"]})
            assert ok.status_code == 200 and ok.json()["first_name"] == u.signup["full_name"].split()[0]
            c.post("/api/auth/logout")
            assert c.post("/api/auth/login", json={"email": u.signup["email"], "password": "wrong-pass-123"}).status_code == 401


def test_demo_accounts_are_distinct_and_look_fictional():
    emails = [u.signup["email"] for u in dd.USERS] + [dd.REVIEWER["email"]]
    assert len(set(emails)) == 4 and all(e.endswith("@example.com") for e in emails)
    assert all(len(u.signup["password"]) >= 8 for u in dd.USERS) and len(dd.REVIEWER["password"]) >= 8


def test_the_published_instructions_match_the_data():
    assert DOCS.exists(), "run: python -m devtools.demo_data"
    assert DOCS.read_text(encoding="utf-8") == dd.render_markdown(), "docs/DEMO_ACCOUNTS.md is stale: run python -m devtools.demo_data"


def test_the_ml_walkthrough_uses_the_same_people_messages_and_scores():
    """ml/reports/phase2_walkthrough.md copies these values by hand-written constants; this keeps the copy honest."""
    text = (DOCS.parent.parent / "ml" / "reports" / "phase2_walkthrough.md").read_text(encoding="utf-8")
    for u in dd.USERS:
        e = u.expected
        assert u.signup["full_name"] in text
        assert u.answers["a1"] in text
        assert f"PHQ-9 {e['phq9']}, GAD-7 {e['gad7']}, C-SSRS tier {e['safety_tier']}" in text
        assert f"| {e['baseline_risk']} |" in text
