# IRIS: Intent and Risk Intelligence System

AI-assisted mental-health support triage: **Baseline assessment, detection, decision, routing, human oversight.**

This repository contains **Module 1: onboarding and clinical baseline** (sign-up, consent, clinical check-in, scoring,
reviewer queue) and a first version of **the chat ("Talk to IRIS") with its human review queue**. In the chat, priority comes
from the rule layer and the check-in safety floor only: **no AI model is used yet**, because none was good enough in the Phase 2
evaluation (`ml/reports/phase2_final_summary.md`). Every message waits for a person, who can raise its priority or record their own
judgement; the system never closes a case. The reply wording is an **AI-assisted draft, clinical review pending**
(`ml/docs/clinical_review/`), so this is a prototype, not for real people. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/TRIAGE_INTEGRATION_SPEC.md](docs/TRIAGE_INTEGRATION_SPEC.md).

| Layer    | Stack                                                                                       |
| -------- | ------------------------------------------------------------------------------------------- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router                                    |
| Backend  | FastAPI, SQLAlchemy 2, Alembic migrations, Pydantic 2                                       |
| Database | Supabase Postgres (Mumbai), Row Level Security on every table                               |
| Auth     | Supabase Auth (email confirmation, password reset); tokens kept in `httpOnly` cookies       |
| Tests    | pytest, 106 tests (scoring, safety tiers, auth flows, role access, audit log, chat and review queue)|

## Set up Supabase (once)

1. Create a project (choose the region closest to your users) and note the **database password**.
2. **Authentication, URL Configuration:** set **Site URL** to `http://localhost:5173` and add
   `http://localhost:5173/**` to **Redirect URLs** (required for confirmation and reset links).
3. **Authentication, Providers, Email:** while developing, either turn **Confirm email** off, or configure a custom
   SMTP provider. Supabase's built-in email service is heavily rate-limited and sends only to project team members.
4. Copy `backend/.env.example` to `backend/.env` and fill in the connection string, project URL and the **anon /
   publishable** key (Project Settings, API). Do **not** use the `service_role` key anywhere in this project.

## Run it locally

Requires Python 3.10+ and Node 20+.

```bash
# 1. Backend  (http://127.0.0.1:8000, API docs at /docs)
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head              # creates the tables, RLS rules and audit log in Supabase (includes 0002, the chat tables: review it first)
uvicorn app.main:app --reload

# 2. Frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

**Make a reviewer:** sign up and sign in once with the reviewer's email, then run
`python -m app.seed promote reviewer@example.com`. The role is stored only in our database, never in user-editable
metadata, so nobody can grant it to themselves.

```bash
cd backend && pytest          # backend tests (no network or database needed)
cd backend && python -m devtools.demo_server   # local sandbox: stand-in sign-in and a throwaway database, see docs/DEMO_ACCOUNTS.md
cd frontend && npm run build  # type-check and production build
```

## Project layout

```
backend/app/
  auth_service.py             Supabase Auth client behind a small interface (faked in tests)
  services/questionnaire.py   clinical intake definition + answer validation (single source of truth)
  services/scoring.py         PHQ-9, GAD-7 and baseline risk (pure functions, unit-tested)
  services/safety.py          self-harm assessment: C-SSRS tiers and the urgency floor
  routers/                    auth, check-in, reviewer (with audit log)
  models.py  schemas.py  deps.py
backend/migrations/           Alembic: schema, foreign key to auth.users, RLS, privileges
backend/tests/
frontend/src/
  pages/                      Login, Register, ForgotPassword, ResetPassword, Consent, CheckIn, Support, Home, Reviewer
  lib/                        typed API client (silent session refresh), questionnaire helpers
```

## Known limitations (deliberate, for this milestone)

- **Guardian consent for under-18s is recorded as `pending` but not verified.** Supabase Auth only emails the person
  signing up, so emailing a guardian needs a separate email service (SMTP or similar).
- No account lockout beyond Supabase's built-in rate limits.
- Reviewer actions (acknowledge, notes, outcome) and the chat/triage pipeline are not built yet.
- The questionnaire is English only. Question text has not yet been reviewed by a clinician (see architecture doc).
