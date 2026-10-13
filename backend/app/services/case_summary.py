"""A summary of a person for the doctor who accepted their case: profile, latest check-in, and what they wrote to IRIS.

Two layers, kept apart on purpose:
* `bullets` are built by plain rules (counts, scores, concerning-language flags). They always work and never leave this server.
* `draft_ai` asks a language model (Groq) for a short narrative. It runs only when the doctor asks, only if the person separately agreed, sends the
  minimum (age band, gender, check-in headline, message text: no name, phone, email or address), and its answer is labelled a draft. It never sets
  priority and never replies to the person. A failure returns None and the rules-based bullets remain.
"""
from __future__ import annotations

import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import age_on
from ..models import CheckIn, ConsultCase, Message
from . import triage

AI_DISCLOSURE = "AI-assisted draft. It can miss or misread things: check it against the messages below."
HISTORY = 12

LANGUAGE_NAME = {"en": "English", "hi": "Hindi", "ml": "Malayalam", "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "bn": "Bengali", "mr": "Marathi",
                 "gu": "Gujarati", "pa": "Punjabi", "ur": "Urdu"}
TOPIC_LABEL = {
    "academic_stress": "study or exam pressure", "work_money": "work or money worries", "relationships": "relationship difficulties",
    "loneliness": "loneliness", "sleep": "sleep problems", "anxiety_worry": "anxiety or worry", "low_mood": "low mood", "grief": "grief or loss",
    "supporting_others": "worry about someone else", "practical_help": "practical help",
}


def _messages(db: Session, user_id) -> list[Message]:
    rows = db.scalars(select(Message).where(Message.user_id == user_id).order_by(Message.id.desc()).limit(HISTORY)).all()
    return list(reversed(rows))


def _latest_checkin(db: Session, user_id) -> CheckIn | None:
    return db.scalar(select(CheckIn).where(CheckIn.user_id == user_id, CheckIn.skipped.is_(False)).order_by(CheckIn.created_at.desc(), CheckIn.id.desc()))


def build(db: Session, case: ConsultCase) -> dict:
    u = case.user
    age = age_on(u.date_of_birth)
    msgs = _messages(db, u.id)
    ck = _latest_checkin(db, u.id)
    scores = (ck.scores if ck else None) or {}
    phq, gad, safety = scores.get("phq9") or {}, scores.get("gad7") or {}, scores.get("safety") or {}

    bullets: list[str] = []
    who = f"{u.full_name.split()[0]}, {age}"
    bits = [b for b in (u.gender, u.occupation) if b]
    lang = LANGUAGE_NAME.get((u.language or "").lower(), u.language)
    bullets.append(f"{who}{' (' + ', '.join(bits) + ')' if bits else ''}. Preferred language: {lang}." + (" Under 18." if age < 18 else ""))
    if ck:
        line = f"Latest check-in: baseline {ck.baseline_risk}"
        if phq.get("score") is not None:
            line += f", PHQ-9 {phq['score']} ({phq.get('band', '')})"
        if gad.get("score") is not None:
            line += f", GAD-7 {gad['score']} ({gad.get('band', '')})"
        bullets.append(line + ".")
        if ck.safety_flag or safety.get("urgency_floor") in ("medium", "high"):
            bullets.append(f"Safety answers raised a {safety.get('urgency_floor', 'flagged')} floor in the check-in.")
    else:
        bullets.append("No completed check-in on file.")
    if msgs:
        flagged = [m for m in msgs if m.prediction and (m.prediction.rule_level != "none" or m.prediction.message_urgent)]
        urgent = [m for m in msgs if m.prediction and m.prediction.message_urgent]
        bullets.append(f"Wrote {len(msgs)} recent message{'s' if len(msgs) != 1 else ''} to IRIS; {len(flagged)} contained concerning language"
                       f"{f', {len(urgent)} explicit' if urgent else ''}.")
        topics: list[str] = []
        for m in msgs:
            for t in triage.support.match_topics(m.text, limit=2):
                label = TOPIC_LABEL.get(t)
                if label and label not in topics:
                    topics.append(label)
        if topics:
            bullets.append("Topics mentioned: " + ", ".join(topics[:5]) + ".")
        last = msgs[-1]
        bullets.append(f"Most recent message: \u201c{last.text.strip()[:160]}{'…' if len(last.text.strip()) > 160 else ''}\u201d")
    else:
        bullets.append("Has not written to IRIS yet.")
    return {
        "profile": {"first_name": u.full_name.split()[0], "age": age, "gender": u.gender, "occupation": u.occupation, "language": u.language,
                    "is_minor": age < 18},
        "checkin": None if ck is None else {
            "created_at": ck.created_at, "baseline_risk": ck.baseline_risk, "phq9": phq.get("score"), "phq9_band": phq.get("band"),
            "gad7": gad.get("score"), "gad7_band": gad.get("band"), "safety_flag": ck.safety_flag, "urgency_floor": safety.get("urgency_floor"),
        },
        "bullets": bullets,
        "recent_messages": [{"text": m.text, "created_at": m.created_at} for m in msgs[-6:]],
    }


SYSTEM_PROMPT = (
    "You help a clinician prepare to speak with a person who asked for a doctor. Summarise ONLY what is in the material, in 4 to 6 short plain sentences "
    "(at most 120 words). State the main concerns the person wrote about, how long or how often they mention them if said, and anything that sounds like "
    "risk, using the person's own words where useful. Say 'not stated' for anything unknown. "
    "Do not diagnose, do not give advice or a plan, do not guess at causes, do not reassure. Never write that there are no risks, no concerns or "
    "nothing else to worry about: the material may be incomplete, so only report what was written. No headings, lists or emojis."
)


def payload_text(db: Session, case: ConsultCase) -> str:
    """The only text that leaves this server for the AI draft: no name, phone, email or address."""
    u = case.user
    ck = _latest_checkin(db, u.id)
    scores = (ck.scores if ck else None) or {}
    age = age_on(u.date_of_birth)
    lines = [f"Person: age {age}" + (f", {u.gender}" if u.gender else "") + (f", {u.occupation}" if u.occupation else "") + "."]
    if ck:
        lines.append(f"Check-in: baseline {ck.baseline_risk}; PHQ-9 {(scores.get('phq9') or {}).get('score')}; GAD-7 {(scores.get('gad7') or {}).get('score')}; "
                     f"safety flag {'yes' if ck.safety_flag else 'no'}.")
    lines.append("Messages the person wrote to a support chat, oldest first:")
    lines += [f"- {m.text.strip()}" for m in _messages(db, u.id)]
    return "\n".join(lines)


def draft_ai(db: Session, case: ConsultCase) -> str | None:
    if not (settings.llm_enabled and settings.groq_api_key):
        return None
    try:
        r = httpx.post(
            f"{settings.groq_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={"model": settings.groq_model, "temperature": 0.2, "max_tokens": 700, "reasoning_effort": "low",
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": payload_text(db, case)}]},
            timeout=max(settings.llm_timeout_seconds, 12.0),
        )
        r.raise_for_status()
        text = " ".join((r.json()["choices"][0]["message"]["content"] or "").split()).strip()
    except Exception:                                                    # noqa: BLE001 - any failure means "no AI draft"
        return None
    if not text or len(text) > 1200 or re.search(r"[\U0001F000-\U0001FFFF]", text):
        return None
    return text
