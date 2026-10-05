# IRIS: Intent and Risk Intelligence System

AI-assisted mental-health support triage: **Baseline assessment, detection, decision, routing, human oversight.**

This repository currently contains **Module 1: onboarding and clinical baseline** (sign-up, consent, clinical
check-in, scoring, reviewer queue). The conversation pipeline (intent, urgency, confidence, cost-sensitive routing)
is the next module and will consume the baseline produced here. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

| Layer    | Stack                                                                 |
| -------- | --------------------------------------------------------------------- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router              |
| Backend  | FastAPI, SQLAlchemy 2, Pydantic 2, SQLite (swap via `IRIS_DATABASE_URL`) |
| Auth     | bcrypt password hashing, JWT in an `httpOnly` `SameSite=Lax` cookie   |
| Tests    | pytest (50 tests: scoring, validation, API, role access)              |

## Run it locally

Requires Python 3.10+ and Node 20+.

```bash
# 1. Backend  (http://127.0.0.1:8000, docs at /docs)
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed reviewer@example.com "choose-a-strong-password"   # creates a reviewer account
uvicorn app.main:app --reload

# 2. Frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Sign up as a normal user to go through consent and the check-in. Sign in with the reviewer account to see the
review queue at `/reviewer`.

```bash
cd backend && pytest          # backend tests
cd frontend && npm run build  # type-check and production build
```

Configuration is via `IRIS_*` environment variables or `backend/.env` (see `backend/.env.example`).
**Set `IRIS_SECRET_KEY` and `IRIS_COOKIE_SECURE=true` for anything other than local development.**

## Project layout

```
backend/app/
  services/questionnaire.py   clinical intake definition + answer validation (single source of truth)
  services/scoring.py         PHQ-9, GAD-7, C-SSRS tier, baseline risk (pure functions, unit-tested)
  routers/                    auth, check-in, reviewer
  models.py  schemas.py  security.py  deps.py
backend/tests/                scoring + API tests
frontend/src/
  pages/                      Login, Register, Consent, CheckIn, Support, Home, Reviewer
  lib/                        typed API client, questionnaire helpers
```

## Known limitations (deliberate, for this milestone)

- **Guardian consent for under-18s is recorded as `pending` but not yet verified** by an emailed link.
- No login rate limiting or account lockout yet. Add before any public deployment.
- No email delivery (password reset, guardian consent). The reviewer account is created with the seed command.
- Reviewer actions (acknowledge, notes, outcome) and the chat/triage pipeline are not built yet.
- The questionnaire is English only. Question text has not yet been reviewed by a clinician (see architecture doc).
