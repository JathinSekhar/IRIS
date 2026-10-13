"""Local test sandbox:   python -m devtools.demo_server   ->  API on http://127.0.0.1:8000

Runs the REAL IRIS backend with two substitutions so you can test by hand with no Supabase and no email:
  * a throwaway SQLite database, deleted and re-created on every start;
  * an in-memory stand-in for Supabase Auth (devtools/fake_auth.py).
It pre-creates only the reviewer (see devtools/demo_data.py). The three demo patients are signed up by hand.

SAFETY: this refuses to start unless it has switched the app to the local SQLite file, so it can never write to a real database.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
DB_FILE = HERE / "demo.db"

# Must happen before the app reads its settings. Environment variables override backend/.env, so Supabase is never reached.
os.environ["IRIS_DATABASE_URL"] = "sqlite:///" + DB_FILE.as_posix()
os.environ["IRIS_SUPABASE_URL"] = ""
os.environ["IRIS_SUPABASE_ANON_KEY"] = ""
sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import db  # noqa: E402
from app.auth_service import get_auth_service  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from devtools.demo_data import DOCTOR, DOCTOR_PROFILE, REVIEWER  # noqa: E402
from devtools.fake_auth import FakeAuth  # noqa: E402

if not db.IS_SQLITE or "demo.db" not in str(db.DATABASE_URL):
    raise SystemExit("refusing to start: the demo sandbox must use its own local SQLite file")

fake = FakeAuth()
app.dependency_overrides[get_auth_service] = lambda: fake


def seed_reviewer() -> None:
    """Create the reviewer through the normal sign-up path, then promote the profile (the role lives only in our database)."""
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json=REVIEWER)
        if r.status_code != 201:
            raise SystemExit(f"could not create the reviewer: {r.status_code} {r.text}")
    with db.SessionLocal() as s:
        user = s.scalar(select(User).where(User.email == REVIEWER["email"]))
        user.role = "reviewer"
        s.commit()


def seed_doctor() -> None:
    """The same path for the test doctor: sign up normally, then the backend sets the role and the profile."""
    from fastapi.testclient import TestClient
    from app.models import DoctorProfile
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json=DOCTOR)
        if r.status_code != 201:
            raise SystemExit(f"could not create the doctor: {r.status_code} {r.text}")
    with db.SessionLocal() as s:
        user = s.scalar(select(User).where(User.email == DOCTOR["email"]))
        user.role = "doctor"
        s.add(DoctorProfile(user_id=user.id, **DOCTOR_PROFILE))
        s.commit()


if __name__ == "__main__":
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(str(DB_FILE) + suffix).unlink(missing_ok=True)
    seed_reviewer()
    seed_doctor()
    print("Sandbox ready. Reviewer:", REVIEWER["email"], "| Doctor:", DOCTOR["email"], "(passwords in docs/DEMO_ACCOUNTS.md)", flush=True)
    print("API on http://127.0.0.1:8000  |  start the website with: cd frontend && npm run dev", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
