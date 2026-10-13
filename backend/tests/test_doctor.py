"""Step 1 of the doctor feature: a doctor role with a profile and an on-duty switch. Only a doctor can use it, and every change is audited."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, DoctorProfile, User
from devtools import demo_data as dd
from tests.test_messages import env, login, signup  # noqa: F401


def make_doctor(c, env, profile=True):
    c.post("/api/auth/logout")
    assert c.post("/api/auth/register", json=dd.DOCTOR).status_code == 201
    with env() as s:
        u = s.scalar(select(User).where(User.email == dd.DOCTOR["email"]))
        u.role = "doctor"
        if profile:
            s.add(DoctorProfile(user_id=u.id, **dd.DOCTOR_PROFILE))
        s.commit()


def test_a_doctor_sees_their_profile_and_starts_off_duty(env):
    with TestClient(app) as c:
        make_doctor(c, env)
        me = c.get("/api/doctor/me").json()
        assert me["full_name"] == dd.DOCTOR["full_name"] and me["on_duty"] is False
        assert me["registration_number"].startswith("TEST-")      # the sandbox doctor never carries a real registration number


def test_going_on_and_off_duty_is_saved_and_audited(env):
    with TestClient(app) as c:
        make_doctor(c, env)
        assert c.post("/api/doctor/availability", json={"on_duty": True}).json()["on_duty"] is True
        assert c.post("/api/doctor/availability", json={"on_duty": True}).status_code == 200      # repeating it changes nothing
        assert c.post("/api/doctor/availability", json={"on_duty": False}).json()["on_duty"] is False
    with env() as s:
        actions = [a.action for a in s.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == ["duty_on", "duty_off"]


def test_a_patient_and_a_reviewer_cannot_use_doctor_endpoints(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert c.get("/api/doctor/me").status_code == 403
        assert c.post("/api/doctor/availability", json={"on_duty": True}).status_code == 403
        c.post("/api/auth/logout")
        assert c.get("/api/doctor/me").status_code == 401


def test_a_doctor_cannot_use_reviewer_endpoints(env):
    with TestClient(app) as c:
        make_doctor(c, env)
        assert c.get("/api/reviewer/messages").status_code == 403


def test_a_doctor_account_without_a_profile_gets_a_clear_error(env):
    with TestClient(app) as c:
        make_doctor(c, env, profile=False)
        assert c.get("/api/doctor/me").status_code == 409


def test_the_role_cannot_be_chosen_at_sign_up(env):
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={**dd.DOCTOR, "role": "doctor"})
        assert r.status_code == 201
        assert c.get("/api/auth/me").json()["role"] == "user"
