import os
import uuid
from datetime import date, datetime, timedelta, timezone

os.environ.setdefault("IRIS_DATABASE_URL", "sqlite://")  # never touch a real database from tests

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_service import get_auth_service
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import AuditLog, CheckIn, User

from devtools.fake_auth import TEST_SECRET, FakeAuth  # noqa: E402  (shared with the demo sandbox)


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def fake():
    return FakeAuth()


@pytest.fixture()
def client(session_factory, fake):
    def _get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_auth_service] = lambda: fake
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


def years_ago(n: int) -> str:
    return date.today().replace(year=date.today().year - n).isoformat()


# --- registration ------------------------------------------------------------------------------------------------

def test_register_sets_httponly_cookies_and_creates_profile(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["confirm_email"] is False
    user = body["user"]
    assert user["email"] == "priya@example.com" and user["first_name"] == "Priya"
    uuid.UUID(user["id"])  # a real UUID shared with the auth user
    cookies = r.headers.get_list("set-cookie")
    assert any(settings.access_cookie in c and "httponly" in c.lower() for c in cookies)
    assert any(settings.refresh_cookie in c and "httponly" in c.lower() and "path=/api/auth" in c.lower() for c in cookies)
    assert "password" not in r.text


def test_register_with_email_confirmation_creates_no_session_until_confirmed(client, fake):
    fake.confirm_required = True
    r = register(client)
    assert r.status_code == 201 and r.json() == {"confirm_email": True, "user": None}
    assert client.get("/api/auth/me").status_code == 401
    # sign-in is refused until the email is confirmed
    bad = client.post("/api/auth/login", json={"email": "priya@example.com", "password": ADULT["password"]})
    assert bad.status_code == 403
    fake.confirm("priya@example.com")
    ok = client.post("/api/auth/login", json={"email": "priya@example.com", "password": ADULT["password"]})
    assert ok.status_code == 200 and ok.json()["first_name"] == "Priya"  # profile built on first sign-in


def test_duplicate_email_conflicts(client):
    register(client)
    assert register(client, email="priya@example.com").status_code == 409


def test_short_password_rejected(client):
    assert register(client, password="short").status_code == 422


def test_under_13_rejected(client):
    assert register(client, date_of_birth=years_ago(10)).status_code == 422


def test_minor_requires_guardian(client):
    dob = years_ago(16)
    assert register(client, date_of_birth=dob).status_code == 422
    r = register(client, date_of_birth=dob, guardian_name="Asha", guardian_email="asha@example.com")
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["is_minor"] is True and user["guardian_consent_status"] == "pending"


# --- sessions ----------------------------------------------------------------------------------------------------

def test_login_logout_and_me(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    wrong = client.post("/api/auth/login", json={"email": "priya@example.com", "password": "nope-nope-nope"})
    ghost = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x"})
    assert wrong.status_code == ghost.status_code == 401 and wrong.json() == ghost.json()  # no user enumeration
    ok = client.post("/api/auth/login", json={"email": "PRIYA@example.com", "password": ADULT["password"]})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").json()["consent_accepted"] is False


def test_forged_or_garbage_token_is_rejected(client):
    client.cookies.set(settings.access_cookie, "not-a-token", path="/")
    assert client.get("/api/auth/me").status_code == 401
    forged = jwt.encode({"sub": str(uuid.uuid4()), "email": "x@example.com", "aud": "authenticated",
                         "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "wrong-secret-wrong-secret-wrong-secret!!",
                        algorithm="HS256")
    client.cookies.set(settings.access_cookie, forged, path="/")
    assert client.get("/api/auth/me").status_code == 401


def test_refresh_restores_an_expired_session(client):
    register(client)
    for c in client.cookies.jar:  # simulate the access token expiring: spoil the existing cookie in place
        if c.name == settings.access_cookie:
            c.value = "expired-or-invalid"
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/refresh").status_code == 204
    assert client.get("/api/auth/me").status_code == 200


def test_refresh_without_cookie_is_unauthorised(client):
    assert client.post("/api/auth/refresh").status_code == 401


def test_forgot_password_never_reveals_whether_an_account_exists(client, fake):
    register(client)
    a = client.post("/api/auth/forgot-password", json={"email": "priya@example.com"})
    b = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert a.status_code == b.status_code == 204


def test_reset_password_changes_the_password(client, fake):
    r = register(client)
    token = client.cookies.get(settings.access_cookie)
    assert token
    client.post("/api/auth/logout")
    assert client.post("/api/auth/reset-password", json={"access_token": token, "password": "a-brand-new-pass-1"}).status_code == 204
    old = client.post("/api/auth/login", json={"email": "priya@example.com", "password": ADULT["password"]})
    new = client.post("/api/auth/login", json={"email": "priya@example.com", "password": "a-brand-new-pass-1"})
    assert old.status_code == 401 and new.status_code == 200
    assert client.post("/api/auth/reset-password", json={"access_token": "x" * 20, "password": "a-brand-new-pass-1"}).status_code == 401


# --- profile metadata is never trusted ---------------------------------------------------------------------------

def test_metadata_cannot_grant_reviewer_role(client, fake):
    register(client, **{})
    client.post("/api/auth/logout")
    # someone calls Supabase sign-up directly with the public key and smuggles in a role
    fake.sign_up("sneaky@example.com", "pw-pw-pw-pw-1", {"full_name": "S", "date_of_birth": "1999-01-01", "role": "reviewer"}, "")
    r = client.post("/api/auth/login", json={"email": "sneaky@example.com", "password": "pw-pw-pw-pw-1"})
    assert r.status_code == 200 and r.json()["role"] == "user"
    assert client.get("/api/reviewer/checkins").status_code == 403


def test_direct_signup_with_invalid_profile_is_refused(client, fake):
    # bypassing our sign-up form: too young, and a minor with no guardian
    fake.sign_up("kid@example.com", "pw-pw-pw-pw-1", {"full_name": "Kid", "date_of_birth": years_ago(9)}, "")
    fake.sign_up("teen@example.com", "pw-pw-pw-pw-1", {"full_name": "Teen", "date_of_birth": years_ago(15)}, "")
    fake.sign_up("blank@example.com", "pw-pw-pw-pw-1", {}, "")
    for email in ("kid@example.com", "teen@example.com", "blank@example.com"):
        assert client.post("/api/auth/login", json={"email": email, "password": "pw-pw-pw-pw-1"}).status_code == 403


# --- consent and check-in ----------------------------------------------------------------------------------------

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
    assert set(body) == {"id", "skipped", "safety_flag", "show_crisis_resources", "offer_doctor", "created_at"}   # offer_doctor is a yes/no, not a score
    assert body["offer_doctor"] is False
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
    register(client)
    accept_consent(client)
    client.post("/api/checkin", json={"answers": {"m1": 0}})
    st = client.get("/api/auth/me").json()["checkin"]
    assert st["state"] == "ok" and st["prompt"] is False

    with session_factory() as s:  # age the check-in beyond the validity window
        row = s.query(CheckIn).one()
        row.created_at = datetime.now(timezone.utc) - timedelta(days=settings.checkin_valid_days + 1)
        s.commit()
    st = client.get("/api/auth/me").json()["checkin"]
    assert st["state"] == "due" and st["prompt"] is True


# --- reviewer access and audit trail -----------------------------------------------------------------------------

def test_reviewer_endpoints_are_role_protected_and_audited(client, session_factory):
    register(client)
    accept_consent(client)
    client.post("/api/checkin", json={"answers": {"s0": 3, "c1": 1, "c2": 1, "c4": 1, "a1": "I cannot cope"}})
    assert client.get("/api/reviewer/checkins").status_code == 403

    # a second person becomes a reviewer (role is set only by the backend, e.g. `python -m app.seed promote`)
    client.post("/api/auth/logout")
    register(client, email="rev@example.com", full_name="Rev One")
    with session_factory() as s:
        rev = s.scalar(select(User).where(User.email == "rev@example.com"))
        rev.role = "reviewer"
        s.commit()
        reviewer_id = rev.id

    queue = client.get("/api/reviewer/checkins").json()
    assert len(queue) == 1
    # the queue is a triage view: no clinical content, contact details or scores
    assert set(queue[0]) == {"id", "user_name", "created_at", "baseline_risk", "safety_flag", "escalated"}
    assert queue[0]["escalated"] is True and queue[0]["baseline_risk"] == "high"

    detail = client.get(f"/api/reviewer/checkins/{queue[0]['id']}").json()
    assert detail["scores"]["safety"]["tier"] == 3 and detail["scores"]["safety"]["urgency_floor"] == "high"
    assert detail["free_text"] == "I cannot cope" and detail["answers"]["c4"] == 1
    uuid.UUID(detail["user_id"])
    assert client.get("/api/reviewer/checkins/9999").status_code == 404  # unknown ids are not logged as views

    with session_factory() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.actor_id == reviewer_id).order_by(AuditLog.id)))   # the reviewer's own actions
    assert [(a.action, a.target_id) for a in rows] == [
        ("list_queue", "1 rows"),
        ("view_checkin", str(queue[0]["id"])),  # which record was opened, by whom
    ]
    assert all(a.actor_id == reviewer_id for a in rows)


def test_every_opening_of_a_record_is_audited_separately(client, session_factory):
    for email in ("a@example.com", "b@example.com"):
        register(client, email=email)
        accept_consent(client)
        client.post("/api/checkin", json={"answers": {"m1": 1}})
        client.post("/api/auth/logout")
    register(client, email="rev2@example.com")
    with session_factory() as s:
        rev = s.scalar(select(User).where(User.email == "rev2@example.com"))
        rev.role = "reviewer"
        s.commit()
    ids = [r["id"] for r in client.get("/api/reviewer/checkins").json()]
    for cid in ids + ids[:1]:  # open both, then the first one again
        assert client.get(f"/api/reviewer/checkins/{cid}").status_code == 200
    with session_factory() as s:
        viewed = [a.target_id for a in s.scalars(select(AuditLog).where(AuditLog.action == "view_checkin").order_by(AuditLog.id))]
    assert viewed == [str(i) for i in ids] + [str(ids[0])]


def test_missing_supabase_keys_give_a_clear_error_not_a_crash(session_factory, monkeypatch):
    from app import auth_service

    monkeypatch.setattr(settings, "supabase_anon_key", "")
    monkeypatch.setattr(auth_service, "_service", None)

    def _get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db  # real get_auth_service on purpose
    try:
        with TestClient(app) as c:
            r = c.post("/api/auth/login", json={"email": "a@example.com", "password": "whatever-1"})
            assert r.status_code == 503 and "not configured" in r.json()["detail"]
            assert c.get("/api/health").status_code == 200
    finally:
        app.dependency_overrides.clear()
