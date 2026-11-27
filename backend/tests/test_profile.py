"""The profile page: a person sees and changes only their own details, and never their email, date of birth, guardian details or role."""
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import User
from devtools import demo_data as dd
from tests.test_messages import env, signup  # noqa: F401

EDIT = {"full_name": "  Ananya   R. Rao ", "gender": "Female", "occupation": "Working", "language": "hi", "phone": " ",
        "emergency_contact": "Suresh Rao, +91 90000 10001"}


def test_not_signed_in_cannot_read_or_change_a_profile(env):
    with TestClient(app) as c:
        assert c.get("/api/profile").status_code == 401
        assert c.post("/api/profile", json=EDIT).status_code == 401


def test_a_person_sees_their_own_details(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        p = c.get("/api/profile").json()
        s = dd.NORMAL.signup
        assert p["full_name"] == s["full_name"] and p["email"] == s["email"] and p["date_of_birth"] == s["date_of_birth"]
        assert p["is_minor"] is False and p["consent_accepted_at"] is not None and p["age"] >= 18


def test_changes_are_saved_tidied_and_shown_in_the_header(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        p = c.post("/api/profile", json=EDIT).json()
        assert p["full_name"] == "Ananya R. Rao" and p["occupation"] == "Working" and p["language"] == "hi"
        assert p["phone"] is None                                   # a blank field is cleared, not stored as spaces
        assert c.get("/api/profile").json()["emergency_contact"] == "Suresh Rao, +91 90000 10001"
        assert c.get("/api/auth/me").json()["full_name"] == "Ananya R. Rao"


def test_email_date_of_birth_guardian_and_role_can_never_be_changed(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        sneaky = {**EDIT, "email": "someone.else@example.com", "date_of_birth": "2015-01-01", "role": "reviewer",
                  "guardian_name": "X", "guardian_consent_status": "granted"}
        assert c.post("/api/profile", json=sneaky).status_code == 200
        p = c.get("/api/profile").json()
        assert p["email"] == dd.NORMAL.signup["email"] and p["date_of_birth"] == dd.NORMAL.signup["date_of_birth"]
        assert p["guardian_name"] is None and p["guardian_consent_status"] is None
        assert c.get("/api/auth/me").json()["role"] == "user"
    with env() as s:
        assert s.scalar(select(User).where(User.email == dd.NORMAL.signup["email"])).role == "user"


def test_bad_values_are_refused(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        for bad in ({**EDIT, "full_name": "   "}, {**EDIT, "phone": "9" * 40}, {**EDIT, "emergency_contact": "x" * 201},
                    {**EDIT, "language": ""}, {k: v for k, v in EDIT.items() if k != "full_name"}):
            assert c.post("/api/profile", json=bad).status_code == 422, bad
        assert c.get("/api/profile").json()["full_name"] == dd.NORMAL.signup["full_name"]


def test_a_minor_sees_their_guardian_and_that_consent_is_waiting(env):
    today = date.today()
    minor = {**dd.NORMAL.signup, "email": "teen.demo@example.com", "date_of_birth": date(today.year - 16, 1, 1).isoformat(),
             "guardian_name": "Asha Rao", "guardian_email": "asha.rao@example.com"}
    with TestClient(app) as c:
        signup(c, minor)
        p = c.get("/api/profile").json()
        assert p["is_minor"] is True and p["guardian_name"] == "Asha Rao" and p["guardian_consent_status"] == "pending"
