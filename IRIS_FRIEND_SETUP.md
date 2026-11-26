# IRIS — Friend Setup Guide

This guide runs the **local demo sandbox**. It does not require a Supabase account or email setup.

## What you need

- Python 3.10 or newer
- Node.js 20 or newer (npm is included)
- VS Code (recommended)

## 1. Extract and open the project

1. Extract `IRIS.zip`.
2. Open the extracted `IRIS` folder in VS Code.
3. Open a terminal in VS Code.

## 2. Install backend dependencies (one time)

In PowerShell on Windows:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks activation, use the venv Python directly in the next step:
`.\.venv\Scripts\python.exe -m devtools.demo_server`

On macOS/Linux, create and install with:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Start the demo backend

Keep the first terminal open.

Windows (PowerShell), from the `backend` folder:

```powershell
.\.venv\Scripts\python.exe -m devtools.demo_server
```

macOS/Linux, from the `backend` folder:

```bash
.venv/bin/python -m devtools.demo_server
```

The API runs at `http://127.0.0.1:8000`.
API documentation: `http://127.0.0.1:8000/docs`.

## 4. Install and start the frontend

Open a **second terminal** in VS Code. From the project root:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`.

## 5. Demo logins

The local sandbox creates a reviewer and a fictional demo doctor automatically.
Use the credentials in `docs/DEMO_ACCOUNTS.md`:

- Reviewer: `reviewer.demo@example.com`
- Doctor: `doctor.demo@example.com`

The three patient demo profiles are not pre-created; the same document contains fictional sign-up details and sample check-in steps.

## Important sandbox behaviour

- The demo server uses a disposable local SQLite database and stand-in authentication.
- It does not connect to Supabase and does not send email.
- The demo database is deleted and recreated each time the demo server starts. Demo accounts and activity therefore reset on restart.
- Use only fictional test information. Do not enter real mental-health or other personal information.
- IRIS is an academic prototype, not a clinical service. It must not be used to assess, diagnose, or provide care to real people.
- The sandbox is for local demonstration on one computer; it is not a public deployment or shared multi-user server.

## Troubleshooting

**`python` is not recognized:** install Python 3.10+ and enable “Add Python to PATH”, then reopen the terminal.

**`npm` is not recognized:** install Node.js 20+ and reopen the terminal.

**Port 8000 or 5173 is already in use:** close the other process using that port, then restart the relevant server.

**Frontend cannot reach the backend:** make sure the backend terminal still shows the API running at `127.0.0.1:8000`, and open the frontend at `localhost:5173`.

**PowerShell blocks virtual-environment activation:** do not activate it; run the backend with `.\.venv\Scripts\python.exe -m devtools.demo_server` as shown above.

## Stop the application

Press `Ctrl+C` in each terminal.
