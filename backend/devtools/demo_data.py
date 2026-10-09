"""Demo accounts and the exact check-in answers for each, for hand testing in the local sandbox.

Single source of truth: `docs/DEMO_ACCOUNTS.md` is GENERATED from this file (`python -m devtools.demo_data`), and an automated
test submits these answers through the real API and checks the expected outcome, so the instructions cannot drift from the system.

Everything here is fictional. These accounts exist only in the throwaway sandbox (`python -m devtools.demo_server`); they are not
Supabase accounts and the passwords are for the sandbox only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.questionnaire import BY_ID, QUESTIONS, is_visible

# Option indices follow the questionnaire definition: frequency 0 = Not at all .. 3 = Nearly every day.
REVIEWER = {"full_name": "Dr. Meera Iyer", "email": "reviewer.demo@example.com", "password": "Demo-Reviewer-2026",
            "date_of_birth": "1985-02-02"}


@dataclass(frozen=True)
class DemoUser:
    key: str
    title: str
    signup: dict
    answers: dict
    expected: dict                      # what the system must produce: used by the test and shown in the docs
    what_you_see: list[str] = field(default_factory=list)


NORMAL = DemoUser(
    key="normal", title="Normal (low risk)",
    signup={"full_name": "Ananya Rao", "email": "ananya.normal@example.com", "password": "Demo-Normal-2026",
            "date_of_birth": "2002-06-14", "gender": "Female", "occupation": "Student", "language": "en",
            "phone": "+91 90000 00001", "emergency_contact": "Suresh Rao, +91 90000 10001"},
    answers={"a1": "Feeling mostly fine, just a bit busy with college this month.", "a2": 0, "a3": [7],
             **{f"m{i + 1}": v for i, v in enumerate([0, 0, 1, 1, 0, 0, 0, 0])},
             **{f"g{i + 1}": v for i, v in enumerate([1, 0, 0, 1, 0, 0, 0])},
             "f1": 0, "f2": 2, "f3": 0, "f4": 0, "f5": 0, "h1": 0, "h2": 0, "h3": 0, "h4": 0, "s0": 0},
    expected={"baseline_risk": "low", "phq9": 2, "phq9_band": "minimal", "gad7": 2, "gad7_band": "minimal",
              "safety_tier": 0, "escalated": False, "show_crisis_resources": False, "queue_position": 3},
    what_you_see=["After the last question the app opens the home page: 'Hi Ananya', check-in completed, next one due in 14 days.",
                  "No crisis or helpline page appears."],
)

MEDIUM = DemoUser(
    key="medium", title="Medium risk",
    signup={"full_name": "Rohit Verma", "email": "rohit.medium@example.com", "password": "Demo-Medium-2026",
            "date_of_birth": "1999-11-03", "gender": "Male", "occupation": "Working", "language": "en",
            "phone": "+91 90000 00002", "emergency_contact": "Neha Verma, +91 90000 10002"},
    answers={"a1": "Exams and money worries are stressing me out and I sleep badly most nights.", "a2": 2, "a3": [0, 3],
             **{f"m{i + 1}": v for i, v in enumerate([2, 2, 1, 2, 1, 2, 1, 1])},
             **{f"g{i + 1}": v for i, v in enumerate([2, 2, 1, 2, 1, 2, 1])},
             "f1": 2, "f2": 1, "f3": 1, "f4": 0, "f5": 1, "h1": 0, "h2": 0, "h3": 1, "h4": 0, "s0": 0},
    expected={"baseline_risk": "medium", "phq9": 12, "phq9_band": "moderate", "gad7": 11, "gad7_band": "moderate",
              "safety_tier": 0, "escalated": False, "show_crisis_resources": False, "queue_position": 2},
    what_you_see=["The app opens the home page (no helpline page), because no self-harm thoughts were reported.",
                  "The reviewer, not you, sees the Medium baseline."],
)

HIGH = DemoUser(
    key="high", title="High risk",
    signup={"full_name": "Arjun Mehta", "email": "arjun.high@example.com", "password": "Demo-High-2026",
            "date_of_birth": "1998-08-20", "gender": "Male", "occupation": "Student", "language": "en",
            "phone": "+91 90000 00003", "emergency_contact": "Kavita Mehta, +91 90000 10003"},
    answers={"a1": "I feel hopeless and I have been thinking about ending my life.", "a2": 3, "a3": [1, 5],
             **{f"m{i + 1}": v for i, v in enumerate([3, 3, 3, 2, 2, 3, 2, 2])},
             **{f"g{i + 1}": v for i, v in enumerate([3, 3, 2, 3, 2, 2, 2])},
             "f1": 3, "f2": 0, "f3": 0, "f4": 0, "f5": 2, "h1": 0, "h2": 0, "h3": 1, "h4": 0,
             "s0": 3, "c1": 1, "c2": 1, "c3": 1, "c4": 1, "c5": 0, "c6": 0},
    expected={"baseline_risk": "high", "phq9": 23, "phq9_band": "severe", "gad7": 17, "gad7_band": "severe",
              "safety_tier": 3, "escalated": True, "show_crisis_resources": True, "queue_position": 1},
    what_you_see=["When you answer the self-harm question, a box with 112, Tele-MANAS 14416 and KIRAN appears straight away.",
                  "Extra safety questions appear one by one (31 -> 34 questions in total).",
                  "After the last question the app opens the support page with the helplines, not the home page."],
)

USERS = [NORMAL, MEDIUM, HIGH]


# --- rendering --------------------------------------------------------------------------------------------------------------------

def _answer_text(qid: str, value) -> str:
    q = BY_ID[qid]
    if isinstance(value, str):
        return f"type: {value}"
    if isinstance(value, list):
        return "select: " + ", ".join(o.label for o in q.options if o.value in value)
    return next(o.label for o in q.options if o.value == value)


def visible_answers(user: DemoUser) -> list[tuple[int, str, str, str]]:
    """(number, question, answer to choose, how it is asked) in the order the app shows them."""
    seen: dict = {}
    rows = []
    for q in QUESTIONS:
        if not is_visible(q, seen):
            continue
        if q.id in user.answers:
            seen[q.id] = user.answers[q.id]
            rows.append((len(rows) + 1, q.prompt, _answer_text(q.id, user.answers[q.id]), q.type))
        else:
            rows.append((len(rows) + 1, q.prompt, "(skip)", q.type))
    return rows


def render_markdown() -> str:
    L: list[str] = []
    w = L.append
    w("# Demo accounts for hand testing\n")
    w("> Generated from `backend/devtools/demo_data.py`. **Do not edit by hand.** An automated test submits exactly these answers "
      "through the real API and checks the results below.\n")
    w("## How to start the sandbox\n")
    w("The sandbox uses a **stand-in login and a throwaway database**. It never touches Supabase, needs no email, and every restart "
      "wipes it clean (only the reviewer is re-created). Start both servers:\n")
    w("```bash\ncd backend && .venv\\Scripts\\python -m devtools.demo_server      # API on http://127.0.0.1:8000\ncd frontend && npm run dev                          # website on http://localhost:5173\n```\n")
    w("Open **http://localhost:5173**. The three patients are **not** pre-created: you sign them up by hand with the details below, "
      "then log out and log in again to test login. The reviewer already exists.\n")
    w("## Reviewer (already created)\n")
    w(f"| Email | Password |\n| --- | --- |\n| `{REVIEWER['email']}` | `{REVIEWER['password']}` |\n")
    w("Sign in as the reviewer after the patients have completed their check-ins. The queue is sorted with the highest urgency first. "
      "Click a name to open the full record (each opening is written to the audit log).\n")
    w("## Other things worth trying (before or between the three users)\n")
    w("- **Wrong password** at login: you get a generic 'Incorrect email or password' message.\n"
      "- **Skip for now** on the check-in (top right): confirm, and the home page offers 'Start check-in' instead of 'completed'.\n"
      "- **Back** and **Clear answer** inside the check-in; single-choice answers move on by themselves, text and multi-select need Next.\n"
      "- **Under 18:** sign up with a birth date less than 18 years ago; the guardian name and email fields appear.\n"
      "- **Forgot password** page: always answers the same, whether or not the email exists.\n"
      "- As a patient, open `/reviewer` in the address bar: you are sent back home. As the reviewer, the home page sends you to the queue.\n")
    for u in USERS:
        s = u.signup
        w(f"## {u.title}: {s['full_name']}\n")
        w("### Sign-up form\n")
        w("| Field | Enter |\n| --- | --- |")
        w(f"| Full name | {s['full_name']} |\n| Email | `{s['email']}` |\n| Password | `{s['password']}` |\n"
          f"| Date of birth | {s['date_of_birth']} (shown as day-month-year in the browser) |\n| Gender | {s['gender']} |\n"
          f"| Occupation | {s['occupation']} |\n| Preferred language | English |\n| Phone (optional) | {s['phone']} |\n"
          f"| Emergency contact (optional) | {s['emergency_contact']} |\n")
        w("Then tick the consent box and **Agree and continue**.\n")
        w("### Check-in answers (in the order the app asks them)\n")
        w("Answer exactly as shown. 'Frequency' questions have four buttons: Not at all, Several days, More than half the days, Nearly every day.\n")
        w("| # | Question | What to choose |\n| --- | --- | --- |")
        for n, prompt, ans, _ in visible_answers(u):
            w(f"| {n} | {prompt.replace('|', '/')} | **{ans}** |")
        e = u.expected
        w("\n### What should happen\n")
        for line in u.what_you_see:
            w(f"- {line}")
        w(f"- **Reviewer view:** baseline risk **{e['baseline_risk'].upper()}**, depression (PHQ-9) **{e['phq9']} / 27 ({e['phq9_band'].replace('_', ' ')})**, "
          f"anxiety (GAD-7) **{e['gad7']} / 21 ({e['gad7_band']})**, suicide-risk screen tier **{e['safety_tier']}**"
          f"{', **escalated**, minimum urgency high' if e['escalated'] else ''}. Position in the queue when all three are done: **{e['queue_position']}**.\n")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[2] / "docs" / "DEMO_ACCOUNTS.md"
    out.write_text(render_markdown(), encoding="utf-8")
    print("wrote", out)
