import os
from datetime import date

os.environ["IRIS_DATABASE_URL"] = "sqlite://"  # in-memory, set before the app imports settings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as app_db
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    def _get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


ADULT = {
    "full_name": "Priya Sharma",
    "email": "Priya@Example.com",
    "password": "correct-horse-battery",
    "date_of_birth": "2000-05-01",
}


def register(client, **over):
    return client.post("/api/auth/register", json={**ADULT, **over})


def accept_consent(client):
    return client.post("/api/consent", json={"version": settings.consent_version})


def test_register_sets_httponly_cookie_and_normalises_email(client):
    r = register(client)
    assert r.status_code == 201
    assert r.json()["email"] == "priya@example.com"
    assert r.json()["first_name"] == "Priya"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "password" not in r.text


def test_duplicate_email_conflicts(client):
    register(client)
    assert register(client, email="priya@example.com").status_code == 409


def test_weak_password_rejected(client):
    assert register(client, password="short").status_code == 422


def test_under_13_rejected(client):
    dob = date.today().replace(year=date.today().year - 10).isoformat()
    assert register(client, date_of_birth=dob).status_code == 422


def test_minor_requires_guardian(client):
    dob = date.today().replace(year=date.today().year - 16).isoformat()
    assert register(client, date_of_birth=dob).status_code == 422
    r = register(client, date_of_birth=dob, guardian_name="Asha", guardian_email="asha@example.com")
    assert r.status_code == 201
    assert r.json()["is_minor"] is True and r.json()["guardian_consent_status"] == "pending"


def test_login_logout_and_me(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "priya@example.com", "password": "nope-nope-nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "PRIYA@example.com", "password": ADULT["password"]}).status_code == 200
    assert client.get("/api/auth/me").json()["consent_accepted"] is False


def test_checkin_requires_auth_and_consent(client):
    assert client.get("/api/checkin/questionnaire").status_code == 401
    register(client)
    assert client.post("/api/checkin", json={"answers": {}}).status_code == 403
    assert accept_consent(client).json()["consent_accepted"] is True


def test_stale_consent_version_rejected(client):
    register(client)
    assert client.post("/api/consent", json={"version": "1999-01"}).status_code == 409


def test_questionnaire_served(client):
    register(client)
    q = client.get("/api/checkin/questionnaire").json()
    ids = [x["id"] for x in q["questions"]]
    assert len(ids) == len(set(ids)) and "s0" in ids and "g7" in ids


def test_submit_returns_no_scores_to_user(client):
    register(client)
    accept_consent(client)
    r = client.post("/api/checkin", json={"answers": {"m1": 3, "m2": 3, "s0": 0}})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "skipped", "safety_flag", "show_crisis_resources", "created_at"}
    assert body["show_crisis_resources"] is False
    assert client.get("/api/auth/me").json()["checkin"]["state"] == "ok"


def test_safety_answer_triggers_crisis_resources(client):
    register(client)
    accept_consent(client)
    r = client.post("/api/checkin", json={"answers": {"s0": 2, "c1": 1, "c2": 1, "c3": 1}})
    assert r.json()["show_crisis_resources"] is True


def test_invalid_answers_rejected(client):
    register(client)
    accept_consent(client)
    assert client.post("/api/checkin", json={"answers": {"m1": 99}}).status_code == 422
    assert client.post("/api/checkin", json={"answers": {"nope": 1}}).status_code == 422


def test_skip_snoozes_checkin_prompt(client):
    register(client)
    accept_consent(client)
    st = client.get("/api/auth/me").json()["checkin"]
    assert st["state"] == "none" and st["prompt"] is True
    assert client.post("/api/checkin", json={"skipped": True}).status_code == 201
    st = client.get("/api/auth/me").json()["checkin"]
    assert st["state"] == "none" and st["prompt"] is False and st["next_due_at"] is not None


def test_completed_checkin_stops_prompting_until_due(client, session_factory):
    from datetime import datetime, timedelta, timezone

    from app.models import CheckIn

    register(client)
    accept_consent(client)
    client.post("/api/checkin", json={"answers": {"m1": 0}})
    st = client.get("/api/auth/me").json()["checkin"]
    assert st["state"] == "ok" and st["prompt"] is False

    # age the check-in beyond the validity window -> due again and prompting
    with session_factory() as s:
        row = s.query(CheckIn).one()
        row.created_at = datetime.now(timezone.utc) - timedelta(days=settings.checkin_valid_days + 1)
        s.commit()
    st = client.get("/api/auth/me").json()["checkin"]
    assert st["state"] == "due" and st["prompt"] is True


def test_reviewer_endpoints_are_role_protected(client, session_factory):
    register(client)
    accept_consent(client)
    client.post("/api/checkin", json={"answers": {"s0": 3, "c1": 1, "c2": 1, "c4": 1, "a1": "I cannot cope"}})
    assert client.get("/api/reviewer/checkins").status_code == 403

    with session_factory() as s:
        s.add(User(email="rev@example.com", password_hash=hash_password("reviewer-pass-1"), role="reviewer",
                   full_name="Rev", date_of_birth=date(1990, 1, 1)))
        s.commit()
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "rev@example.com", "password": "reviewer-pass-1"}).status_code == 200
    rows = client.get("/api/reviewer/checkins").json()
    assert len(rows) == 1
    assert rows[0]["escalated"] is True and rows[0]["baseline_risk"] == "high"
    assert rows[0]["scores"]["safety"]["tier"] == 3
    assert rows[0]["free_text"] == "I cannot cope"
    assert client.get(f"/api/reviewer/checkins/{rows[0]['id']}").status_code == 200
    assert client.get("/api/reviewer/checkins/9999").status_code == 404
