# Putting the IRIS demo online (Render)

This puts the **sandbox** online as one web service: the same thing as the local demo and the demo video. Stand-in sign-in, a throwaway
database and fictional accounts. It is a prototype that no clinician has reviewed, so it always sits behind an **access password**: share the
link and the password only with your reviewers.

## What the reviewers get
1. The link opens the public **landing page** (what IRIS is, how it works, safety, helplines). The landing page and the
   Emergency Support page are open to anyone; they show no data.
2. **Sign in** or **Create an account** opens the **IRIS demo** page asking for the access password, then the normal app. They can sign up a fictional student, or sign in with the accounts in [DEMO_ACCOUNTS.md](DEMO_ACCOUNTS.md)
   (reviewer `reviewer.demo@example.com`, doctor `doctor.demo@example.com`).

## Deploy (about 10 minutes, once)
1. Push this repository to GitHub (it already is: `JathinSekhar/IRIS`).
2. Create a free account at **render.com** and connect your GitHub account.
3. **New, Blueprint**, pick the `IRIS` repository. Render reads `render.yaml` and creates the service `iris-demo`.
4. It asks for two secret values. Type them in Render only, never in the repository:
   - `IRIS_DEMO_PASSWORD`: the access password you will give your reviewers (long and not used anywhere else).
   - `IRIS_GROQ_API_KEY`: your Groq key for the AI reply (the same as in `backend/.env`). Leave it empty to run without the AI reply.
5. **Apply**. The first build takes about 5 to 10 minutes. The link looks like `https://iris-demo-xxxx.onrender.com`.

## Good to know
- **Free plan sleeps** after about 15 minutes without visitors. The next visit wakes it in about a minute, and every wake-up starts with
  a **clean database** (only the reviewer and doctor exist). Open the link a few minutes before your review, and do not rely on data
  from yesterday.
- After a restart, reviewers type the access password again.
- Video calls use a public STUN server and no TURN relay, so they can fail on some networks. The chat keeps working.
- The demo reviewer and doctor passwords are in this repository, so anyone who has the access password can sign in as them.
  That is fine for fictional data, and is the reason the access password is required.
- To take it offline: Render dashboard, the service, **Suspend** (or Delete).

## Try the online mode locally
```bash
cd frontend && npm run build
cd ../backend
IRIS_DEMO_WEB_DIR=../frontend/dist IRIS_DEMO_PASSWORD=choose-one PORT=8090 .venv/Scripts/python -m devtools.demo_server
```
Then open http://localhost:8090. Or with Docker (Docker Desktop running): `docker build -t iris-demo .` and
`docker run -p 8000:8000 -e IRIS_DEMO_PASSWORD=choose-one iris-demo`.
