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

import secrets  # noqa: E402

from devtools import fake_auth  # noqa: E402

# A fresh signing secret on every start: the fixed test secret is public in this repository, so tokens could otherwise be forged.
fake_auth.TEST_SECRET = secrets.token_urlsafe(48)
fake = FakeAuth()

# ---- online mode (used by the Dockerfile; all off by default) --------------------------------------------------------------------------------
#   IRIS_DEMO_WEB_DIR   the built website (frontend/dist): served from this same server, so one service is the whole demo
#   IRIS_DEMO_PASSWORD  an access password for EVERYTHING (a small password page, then a cookie), so only invited reviewers can open it
#   IRIS_DEMO_HOST / PORT  where to listen (a host such as Render sets PORT)
WEB_DIR = os.environ.get("IRIS_DEMO_WEB_DIR")
ACCESS_PASSWORD = os.environ.get("IRIS_DEMO_PASSWORD", "")

ACCESS_COOKIE = "iris_access"
# Open to anyone, even before the access password: they show no data (the API behind them stays closed).
PUBLIC_PAGES = {"/", "/emergency", "/favicon.svg"}
ACCESS_TOKEN = secrets.token_urlsafe(32)          # a new token on every start: after a restart reviewers type the password again

ACCESS_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IRIS demo</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f8fafc;font:16px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;color:#1e293b}
form{width:min(92vw,380px);background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:32px;box-shadow:0 2px 8px rgba(15,23,42,.06)}
h1{margin:0 0 4px;font-size:22px;color:#1c4143}p{margin:0 0 20px;font-size:14px;color:#475569}
label{display:block;font-size:14px;font-weight:600;margin-bottom:6px}
input{box-sizing:border-box;width:100%;height:44px;border:1px solid #cbd5e1;border-radius:8px;padding:0 12px;font-size:15px}
button{margin-top:16px;width:100%;height:44px;border:0;border-radius:8px;background:#1e4d4f;color:#fff;font-size:15px;font-weight:600;cursor:pointer}
.err{color:#b91c1c;font-size:14px;margin:10px 0 0}.note{margin:18px 0 0;font-size:12px;color:#64748b}</style></head>
<body><form method="post" action="/__access"><h1>IRIS demo</h1>
<p>This prototype is for invited reviewers only. Enter the access password you were given.</p>
<label for="pw">Access password</label><input id="pw" name="password" type="password" autocomplete="current-password" autofocus required>
<input type="hidden" name="next" value="{next}">{error}<button type="submit">Continue</button>
<p class="note">A student mental-health support prototype. Not clinically reviewed and not for real use: all accounts are fictional.
If you need help right now, call 112 or Tele-MANAS 14416.</p></form></body></html>"""

if ACCESS_PASSWORD:
    import asyncio
    import html
    from urllib.parse import parse_qs

    from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

    def _access_page(next_path: str, error: bool = False, status: int = 200) -> HTMLResponse:
        err = '<p class="err" role="alert">That password is not right.</p>' if error else ""
        return HTMLResponse(ACCESS_PAGE.replace("{next}", html.escape(next_path, quote=True)).replace("{error}", err), status_code=status,
                            headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def _access_password(request, call_next):
        path = request.url.path
        if path == "/api/health":                                   # the host's health check
            return await call_next(request)
        if request.method == "GET" and (path in PUBLIC_PAGES or path.startswith("/assets/")):
            return await call_next(request)                         # the landing page, emergency help and the site's own files are public; no data
        if path == "/__access" and request.method == "POST":
            form = parse_qs((await request.body()).decode("utf-8", "replace"))
            pw = (form.get("password") or [""])[0]
            nxt = (form.get("next") or ["/"])[0]
            if not nxt.startswith("/") or nxt.startswith("//"):     # only paths on this site, never another site
                nxt = "/"
            if not secrets.compare_digest(pw, ACCESS_PASSWORD):
                await asyncio.sleep(1.0)                            # slows down guessing
                return _access_page(nxt, error=True, status=401)
            res = RedirectResponse(nxt, status_code=303)
            res.set_cookie(ACCESS_COOKIE, ACCESS_TOKEN, httponly=True, samesite="lax", secure=os.environ.get("IRIS_COOKIE_SECURE") == "true",
                           max_age=12 * 3600)
            return res
        if secrets.compare_digest(request.cookies.get(ACCESS_COOKIE, ""), ACCESS_TOKEN):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Access password required."}, status_code=401)
        return _access_page(path if request.method == "GET" else "/", status=401)

# The sandbox creates its reviewer and doctor through its own API, so those set-up calls carry the access password too.
_SETUP_HEADERS = {"Cookie": f"{ACCESS_COOKIE}={ACCESS_TOKEN}"} if ACCESS_PASSWORD else {}

if WEB_DIR:
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    web = Path(WEB_DIR).resolve()
    app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def _website(path: str):
        """Files from the built site; any other page is the single-page app (React Router handles it). Unknown /api paths stay 404."""
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (web / path).resolve()
        if path and f.is_file() and web in f.parents:
            return FileResponse(f)
        return FileResponse(web / "index.html")
app.dependency_overrides[get_auth_service] = lambda: fake


def seed_reviewer() -> None:
    """Create the reviewer through the normal sign-up path, then promote the profile (the role lives only in our database)."""
    from fastapi.testclient import TestClient
    with TestClient(app, headers=_SETUP_HEADERS) as c:
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
    with TestClient(app, headers=_SETUP_HEADERS) as c:
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
    host, port = os.environ.get("IRIS_DEMO_HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))
    if WEB_DIR:
        print(f"Website and API on http://{host}:{port}" + ("  (access password on)" if ACCESS_PASSWORD else "  (NO access password)"), flush=True)
    else:
        print(f"API on http://{host}:{port}  |  start the website with: cd frontend && npm run dev", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")
