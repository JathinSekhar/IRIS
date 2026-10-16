"""Record the IRIS demo video: Priya (low risk) and Rahul (high risk), the reviewer, and the doctor, with on-screen captions.

LOCAL SANDBOX ONLY, fictional people. Needs a FRESH sandbox (python -m devtools.demo_server) and the web app (npm run dev) running, and
Playwright (`pip install playwright` and `python -m playwright install chromium`). Writes demo_video/IRIS_demo.webm in the repository root.

    cd backend && python -m devtools.record_demo
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("IRIS_DATABASE_URL", "sqlite:///" + (ROOT / "backend" / "devtools" / "demo.db").as_posix())

from app.services import questionnaire as qn  # noqa: E402
from devtools import demo_data as dd  # noqa: E402

API = "http://127.0.0.1:8000"
WEB = "http://localhost:5173"
OUT = ROOT / "demo_video"

PRIYA = {"full_name": "Priya Sharma", "email": "priya.demo@example.com", "password": "Priya-Demo-2026", "dob": "2002-03-14",
         "gender": "Female", "phone": "+91 90000 00021", "contact": "Anita Sharma, +91 90000 10021"}
RAHUL = {"full_name": "Rahul Verma", "email": "rahul.demo@example.com", "password": "Rahul-Demo-2026", "dob": "1998-07-02",
         "gender": "Male", "phone": "+91 90000 00022", "contact": "Vikram Verma, +91 90000 10022"}
DOCTOR = {"full_name": "Dr. Sameer Khan", "email": "sameer.demo@example.com", "password": "Sameer-Demo-2026", "date_of_birth": "1984-09-21"}
DOCTOR_PROFILE = {"specialty": "Psychiatry (test account)", "registration_number": "TEST-000111 (not a real registration)",
                  "languages": ["English", "Hindi", "Telugu"]}

PRIYA_ANSWERS = {**dd.NORMAL.answers, "a1": "Exams are next week and I can't focus.", "a3": [0]}
RAHUL_ANSWERS = {**dd.HIGH.answers, "a1": "I feel hopeless and nothing seems worth it any more."}

OVERLAY = """
(() => {
  if (window.__irisOverlay) return; window.__irisOverlay = true;
  const ready = (fn) => document.body ? fn() : document.addEventListener('DOMContentLoaded', fn);
  ready(() => {
    const cap = document.createElement('div');
    cap.id = '__cap';
    cap.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:80%;padding:12px 22px;border-radius:14px;' +
      'background:rgba(15,23,42,.88);color:#fff;font:600 21px/1.35 system-ui,sans-serif;text-align:center;z-index:2147483646;' +
      'box-shadow:0 8px 30px rgba(0,0,0,.25);transition:opacity .3s;opacity:0;pointer-events:none';
    document.body.appendChild(cap);
    const card = document.createElement('div');
    card.id = '__card';
    card.style.cssText = 'position:fixed;inset:0;display:none;align-items:center;justify-content:center;flex-direction:column;gap:18px;' +
      'background:linear-gradient(135deg,#0f3b3a,#134e4a);color:#fff;z-index:2147483647;text-align:center;padding:40px;font-family:system-ui,sans-serif';
    document.body.appendChild(card);
    const dot = document.createElement('div');
    dot.style.cssText = 'position:fixed;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(234,88,12,.55);' +
      'border:2px solid rgba(255,255,255,.9);z-index:2147483645;pointer-events:none;left:-40px;top:-40px;transition:left .15s,top .15s';
    document.body.appendChild(dot);
    document.addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
    window.__cap = (t) => { cap.textContent = t; cap.style.opacity = t ? '1' : '0'; };
    window.__card = (title, sub) => {
      card.innerHTML = '<div style="font-size:46px;font-weight:700;max-width:900px;line-height:1.2"></div><div style="font-size:24px;opacity:.85;max-width:900px;line-height:1.4"></div>';
      card.children[0].textContent = title; card.children[1].textContent = sub || ''; card.style.display = 'flex';
    };
    window.__uncard = () => { card.style.display = 'none'; };
  });
})();
"""


# ----------------------------------------------------------------------------------------------------------------------------------- helpers
def say(page: Page, text: str, secs: float = 3.5) -> None:
    page.wait_for_function("() => typeof window.__cap === 'function'", timeout=10000)
    page.evaluate("t => window.__cap(t)", text)
    page.wait_for_timeout(int(secs * 1000))


def card(page: Page, title: str, sub: str = "", secs: float = 4.0) -> None:
    page.wait_for_function("() => typeof window.__card === 'function'", timeout=10000)
    page.evaluate("([t, s]) => { window.__cap(''); window.__card(t, s); }", [title, sub])
    page.wait_for_timeout(int(secs * 1000))
    page.evaluate("() => window.__uncard()")


def click(page: Page, locator, pause: float = 0.6) -> None:
    locator.first.scroll_into_view_if_needed()
    box = locator.first.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=12)
    page.wait_for_timeout(250)
    locator.first.click()
    page.wait_for_timeout(int(pause * 1000))


def type_into(page: Page, locator, text: str, delay: int = 28) -> None:
    click(page, locator, pause=0.2)
    locator.first.press_sequentially(text, delay=delay)


def login(page: Page, email: str, password: str) -> None:
    page.goto(f"{WEB}/login")
    page.wait_for_selector("input[type=email]")
    type_into(page, page.locator("input[type=email]"), email, delay=12)
    type_into(page, page.locator("input[type=password]"), password, delay=12)
    click(page, page.get_by_role("button", name="Sign in"), pause=2.0)


def logout(page: Page) -> None:
    page.evaluate("() => window.__cap && window.__cap('')")
    click(page, page.get_by_role("button", name="Log out"), pause=1.2)


def api_client(email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=API, timeout=30)
    assert c.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200
    return c


def setup_doctor() -> None:
    """Create Dr. Sameer through the normal sign-up, then give the role and profile in the sandbox database (as the sandbox seeds its doctor)."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models import DoctorProfile, User

    with httpx.Client(base_url=API, timeout=30) as c:
        r = c.post("/api/auth/register", json=DOCTOR)
        assert r.status_code == 201, r.text
    with Session(create_engine(os.environ["IRIS_DATABASE_URL"])) as s:
        u = s.scalar(select(User).where(User.email == DOCTOR["email"]).order_by(User.created_at.desc()))
        u.role = "doctor"
        s.add(DoctorProfile(user_id=u.id, on_duty=False, **DOCTOR_PROFILE))
        s.commit()


# --------------------------------------------------------------------------------------------------------------------------------- scenes
def sign_up(page: Page, p: dict) -> None:
    page.goto(f"{WEB}/login")
    click(page, page.get_by_role("link", name="Create an account"), pause=1.0)
    type_into(page, page.get_by_label("Full name"), p["full_name"])
    type_into(page, page.get_by_label("Email"), p["email"], delay=15)
    type_into(page, page.get_by_label("Password"), p["password"], delay=15)
    page.get_by_label("Date of birth").fill(p["dob"])
    page.get_by_label("Gender").select_option(p["gender"])
    page.get_by_label("Occupation").select_option("Student")
    page.get_by_label("Phone").fill(p["phone"])
    page.get_by_label("Emergency contact").fill(p["contact"])
    page.wait_for_timeout(600)
    click(page, page.get_by_role("button", name="Create account"), pause=2.0)


def consent(page: Page) -> None:
    page.wait_for_url(re.compile(r"/consent"))
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(800)
    click(page, page.get_by_role("checkbox"), pause=0.4)
    click(page, page.get_by_role("button", name="Agree and continue"), pause=1.5)


def check_in(page: Page, answers: dict, fast: bool, on_question=None) -> None:
    page.wait_for_url(re.compile(r"/check-in"))
    questions = qn.QUESTIONNAIRE.model_dump()["questions"]
    seen = set()
    for _ in range(80):
        if "/check-in" not in page.url:
            return
        heading = page.locator("#q-prompt")
        heading.wait_for(timeout=10000)
        prompt = heading.inner_text().strip()
        q = next(x for x in questions if prompt.startswith(x["prompt"][:40]))
        if q["id"] in seen:                       # still on the same question: the last one, press Finish
            click(page, page.get_by_role("button", name=re.compile("Finish|Next")), pause=2.0)
            continue
        seen.add(q["id"])
        if on_question:
            on_question(q["id"])
        a = answers.get(q["id"])
        pause = 0.35 if fast else 0.8
        if q["type"] == "text":
            type_into(page, page.locator("textarea"), a or "", delay=18)
            click(page, page.get_by_role("button", name=re.compile("^(Next|Finish)")), pause=pause)
        elif q["type"] == "multi":
            for v in a or []:
                label = next(o["label"] for o in q["options"] if o["value"] == v)
                click(page, page.locator("fieldset label").get_by_text(label, exact=True), pause=0.2)
            click(page, page.get_by_role("button", name=re.compile("^(Next|Finish)")), pause=pause)
        else:
            label = next(o["label"] for o in q["options"] if o["value"] == a)
            click(page, page.locator("fieldset label").get_by_text(label, exact=True), pause=pause)
        page.wait_for_timeout(250)


def doctor_chat(page: Page, person: httpx.Client, lines: list[tuple[str, str]]) -> None:
    case_id = person.get("/api/consults/current").json()["id"]
    box = page.get_by_placeholder("Write to the person")
    for who, text in lines:
        if who == "doctor":
            type_into(page, box, text, delay=22)
            box.press("Enter")
            page.wait_for_timeout(1500)
        else:
            page.wait_for_timeout(1200)
            assert person.post(f"/api/consults/{case_id}/messages", json={"text": text}).status_code == 201
            page.get_by_text(text, exact=True).wait_for(timeout=15000)
            page.wait_for_timeout(1800)


def fill_note(page: Page, note: dict) -> None:
    click(page, page.get_by_role("button", name="End session and complete the form"), pause=1.0)

    def area(label: str, text: str) -> None:
        type_into(page, page.locator(f"label:has-text('{label}') textarea"), text, delay=8)

    area("What the person reported", note["concerns"])
    for group, answer in note["risk"].items():
        click(page, page.get_by_role("radiogroup", name=group).get_by_role("radio", name=answer, exact=True), pause=0.2)
    area("Protective factors", note["protective"])
    page.locator("label:has-text('Your overall risk judgement') select").select_option(note["risk_level"])
    page.locator("label:has-text('Safety plan') select").select_option(note["safety_plan"])
    if note["safety_plan"] != "not_needed":
        click(page, page.get_by_text("The person received a copy of the safety plan"), pause=0.2)
    area("Actions taken", note["actions"])
    area("Follow-up plan", note["follow_up"])
    page.locator("input[type=date]").fill((date.today() + timedelta(days=note["follow_up_days"])).isoformat())
    page.wait_for_timeout(800)
    click(page, page.get_by_role("button", name="Save and end session"), pause=2.0)


# ----------------------------------------------------------------------------------------------------------------------------------- story
def run() -> Path:
    setup_doctor()
    OUT.mkdir(exist_ok=True)
    raw = OUT / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(raw), record_video_size={"width": 1280, "height": 720})
        ctx.add_init_script(OVERLAY)
        page = ctx.new_page()

        # ---- opening
        page.goto(f"{WEB}/login")
        card(page, "IRIS", "Support that never leaves a student alone", 4)
        card(page, "Many students in distress wait too long to ask for help.", "IRIS: a check-in, a chat, a team that reads every message, and a doctor when needed.", 5)

        # ---- Priya, low risk
        card(page, "Priya", "A student with exams next week", 3)
        say(page, "Priya creates an account.", 1.5)
        sign_up(page, PRIYA)
        say(page, "Before anything, IRIS explains what it is, and what it is not.", 2.5)
        consent(page)
        say(page, "A short check-in: mood, anxiety, daily life and safety questions.", 1.0)
        check_in(page, PRIYA_ANSWERS, fast=True)
        page.wait_for_url(re.compile(r"/$"))
        say(page, "Low risk. No alarms: Priya lands on her home page.", 3)
        click(page, page.get_by_role("link", name="Start talking"), pause=1.2)
        say(page, "Priya talks to IRIS.", 1.5)
        box = page.get_by_placeholder("Write here")
        type_into(page, box, "I'm stressed about my exams next week and I can't focus.", delay=30)
        box.press("Enter")
        page.get_by_text("Did this help?").wait_for(timeout=30000)
        say(page, "IRIS suggests simple steps first, and asks a gentle question.", 4.5)
        click(page, page.get_by_role("button", name="More ideas"), pause=1.5)
        say(page, "If the suggestions are not enough...", 2)
        click(page, page.get_by_role("button", name="Not really"), pause=1.5)
        say(page, "...IRIS offers a doctor. Nothing is shared until Priya agrees.", 3.5)
        click(page, page.get_by_role("region", name="Talk to a doctor").get_by_role("checkbox").first, pause=0.6)
        click(page, page.get_by_role("button", name="Yes, find a doctor"), pause=2.0)
        say(page, "IRIS never promises help it cannot guarantee. The helplines are always there.", 4.5)
        logout(page)

        # ---- Rahul, high risk
        card(page, "Rahul", "A student who has been struggling for months", 3)
        sign_up(page, RAHUL)
        consent(page)
        say(page, "Rahul's answers show he is struggling.", 1.0)

        def rahul_q(qid: str) -> None:
            if qid == "c1":
                say(page, "A worrying answer shows helplines at once, in the middle of the check-in.", 4.5)

        check_in(page, RAHUL_ANSWERS, fast=False, on_question=rahul_q)
        page.wait_for_url(re.compile(r"/support"))
        say(page, "After the check-in: helplines, and an offer to talk to a doctor.", 4.5)
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(1500)
        page.goto(f"{WEB}/chat")
        say(page, "Rahul writes to IRIS.", 1.5)
        box = page.get_by_placeholder("Write here")
        type_into(page, box, "I can't sleep and everything feels pointless.", delay=32)
        box.press("Enter")
        page.wait_for_timeout(4000)
        say(page, "A careful reply with helplines. Never a quick tip.", 3.5)
        click(page, page.get_by_role("region", name="Talk to a doctor").get_by_role("checkbox").first, pause=0.6)
        say(page, "Rahul agrees to share, and asks for a doctor.", 2)
        click(page, page.get_by_role("button", name="Yes, find a doctor"), pause=2.0)
        say(page, "His request is marked urgent. He is told the truth while he waits.", 4)
        logout(page)

        # ---- reviewer
        card(page, "The team", "A person reads every message", 3)
        login(page, dd.REVIEWER["email"], dd.REVIEWER["password"])
        say(page, "Urgent requests raise an alert for the review team.", 3.5)
        click(page, page.get_by_role("tab", name=re.compile("Messages")) if page.get_by_role("tab", name=re.compile("Messages")).count()
              else page.get_by_role("button", name=re.compile("^Messages")), pause=1.5)
        say(page, "Every message waits in a queue, sorted by priority. Software never closes a case.", 4.5)
        logout(page)

        # ---- doctor
        card(page, "The doctor", "Dr. Sameer Khan, on the IRIS team (fictional)", 3)
        login(page, DOCTOR["email"], DOCTOR["password"])
        say(page, "Dr. Sameer goes on duty.", 1.5)
        click(page, page.get_by_role("switch", name="On duty"), pause=2.5)
        say(page, "Urgent requests come first. Before accepting, a doctor sees only age and urgency.", 5)
        click(page, page.get_by_role("button", name="Accept").first, pause=2.0)
        rahul_case = page.locator("article", has_text="Rahul")
        say(page, "After accepting, a short summary from Rahul's check-in and chat.", 4)
        click(page, rahul_case.get_by_role("link", name="Review and start"), pause=2.5)
        say(page, "The full summary sits beside the conversation.", 4)
        click(page, page.get_by_role("button", name="Start conversation"), pause=2.0)
        say(page, "The doctor starts the conversation.", 1.5)
        rahul = api_client(RAHUL["email"], RAHUL["password"])
        doctor_chat(page, rahul, [
            ("doctor", "Hi Rahul, I'm Dr. Sameer. Thank you for reaching out. How are you feeling right now?"),
            ("person", "Tired. Everything feels pointless lately."),
            ("doctor", "I'm glad you told me. Are you safe right now, and is someone with you today?"),
            ("person", "My roommate is here."),
            ("doctor", "Good. Let's make a simple safety plan together, and keep Tele-MANAS 14416 close if things get worse tonight."),
            ("person", "Okay. Thank you."),
        ])
        say(page, "Video calls are available too (not shown here).", 3)
        logout(page)
        login(page, RAHUL["email"], RAHUL["password"])
        page.goto(f"{WEB}/talk-to-a-doctor")
        page.wait_for_timeout(2500)
        say(page, "Rahul sees a real doctor, with their registration number.", 4.5)
        logout(page)
        login(page, DOCTOR["email"], DOCTOR["password"])
        click(page, page.locator("article", has_text="Rahul").get_by_role("link"), pause=2.5)
        say(page, "Every session ends with a documented note.", 2)
        fill_note(page, {
            "concerns": "Hopeless for months, poor sleep, feels everything is pointless.",
            "risk": {"Thoughts of suicide or self-harm": "Yes", "Has a plan": "No", "Intent to act": "No", "Access to means": "No", "Previous attempt": "No"},
            "protective": "Roommate present; wants to finish his degree.", "risk_level": "high", "safety_plan": "created",
            "actions": "Listened, made a safety plan together, shared helplines.", "follow_up": "Check in tomorrow.", "follow_up_days": 1,
        })

        click(page, page.get_by_role("button", name="Accept").first, pause=2.0)
        click(page, page.locator("article", has_text="Priya").get_by_role("link", name="Review and start"), pause=2.5)
        say(page, "Priya gets help too.", 1.5)
        click(page, page.get_by_role("button", name="Start conversation"), pause=2.0)
        priya = api_client(PRIYA["email"], PRIYA["password"])
        doctor_chat(page, priya, [
            ("doctor", "Hi Priya, I'm Dr. Sameer. Exams are on your mind. What feels hardest right now?"),
            ("person", "I keep studying but nothing sticks, and I'm sleeping late."),
            ("doctor", "That's common before exams. Shall we plan your next three days, with breaks and a fixed bedtime?"),
            ("person", "Yes, that would help."),
        ])
        fill_note(page, {
            "concerns": "Exam stress, poor focus, late nights.",
            "risk": {"Thoughts of suicide or self-harm": "No", "Has a plan": "No", "Intent to act": "No", "Access to means": "Not assessed", "Previous attempt": "No"},
            "protective": "Supportive family; motivated to study.", "risk_level": "low", "safety_plan": "not_needed",
            "actions": "Planned a three-day study timetable with breaks and a fixed bedtime.", "follow_up": "Check in after the exams.", "follow_up_days": 7,
        })

        # ---- closing
        card(page, "Rules plus people, not a black box.", "A person reads every message. Consent before sharing. No false promises.", 5)
        card(page, "IRIS", "Prototype: not yet clinically reviewed, not for real use. All people shown are fictional; the doctor's words are illustrative.", 5)

        video = page.video
        ctx.close()
        browser.close()
        src = Path(video.path())
    final = OUT / "IRIS_demo.webm"
    shutil.move(str(src), final)
    shutil.rmtree(raw, ignore_errors=True)
    return final


if __name__ == "__main__":
    t0 = time.time()
    out = run()
    print(f"recorded {out} in {time.time() - t0:.0f}s")
