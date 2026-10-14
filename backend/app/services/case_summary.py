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

AI_DISCLOSURE = "AI-assisted draft. It can miss or misread things: check it against what the person wrote."
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

    chat = {"count": len(msgs), "concerning": 0, "explicit": 0, "topics": [], "latest": None}
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
        chat["concerning"], chat["explicit"] = len(flagged), len(urgent)
        bullets.append(f"Wrote {len(msgs)} recent message{'s' if len(msgs) != 1 else ''} to IRIS; {len(flagged)} contained concerning language"
                       f"{f', {len(urgent)} explicit' if urgent else ''}.")
        topics: list[str] = []
        for m in msgs:
            for t in triage.support.match_topics(m.text, limit=2):
                label = TOPIC_LABEL.get(t)
                if label and label not in topics:
                    topics.append(label)
        chat["topics"] = topics[:5]
        if topics:
            bullets.append("Topics mentioned: " + ", ".join(topics[:5]) + ".")
        last = msgs[-1]
        chat["latest"] = last.text.strip()[:240]
        bullets.append(f"Most recent message: \u201c{last.text.strip()[:160]}{'…' if len(last.text.strip()) > 160 else ''}\u201d")
    else:
        bullets.append("Has not written to IRIS yet.")
    return {
        "profile": {"first_name": u.full_name.split()[0], "age": age, "gender": u.gender, "occupation": u.occupation, "language": u.language,
                    "language_name": LANGUAGE_NAME.get((u.language or "").lower(), u.language), "is_minor": age < 18},
        "checkin": None if ck is None else {
            "created_at": ck.created_at, "baseline_risk": ck.baseline_risk, "phq9": phq.get("score"), "phq9_band": phq.get("band"),
            "gad7": gad.get("score"), "gad7_band": gad.get("band"), "safety_flag": ck.safety_flag, "urgency_floor": safety.get("urgency_floor"),
        },
        "bullets": bullets,
        "chat": chat,
        "recent_messages": [{"text": m.text, "created_at": m.created_at} for m in msgs[-6:]],
    }


SYSTEM_PROMPT = (
    "You help a clinician prepare to speak with a person who asked for a doctor. Read ONLY the material and reply with ONE JSON object, nothing else:\n"
    '{"concerns": [..], "how_long": ".." or null, "quote": ".." or null, "worrying_phrases": [..]}\n'
    "concerns: up to 4 short plain phrases (3 to 8 words each) naming what the person wrote about, e.g. \"cannot sleep before exams\".\n"
    "how_long: how long or how often, only if the person said it (e.g. \"two weeks\"), otherwise null.\n"
    "quote: one sentence copied EXACTLY from the person's messages that best shows how they feel, otherwise null.\n"
    "worrying_phrases: words copied EXACTLY from the messages that sound like hopelessness, self-harm or not wanting to live; [] if none.\n"
    "Never diagnose, advise, guess causes or reassure. Never say there is no risk or nothing else. Do not mention scores or questionnaires."
)


def payload_text(db: Session, case: ConsultCase) -> str:
    """The only text that leaves this server for the AI draft: no name, phone, email or address."""
    u = case.user
    age = age_on(u.date_of_birth)
    # The check-in scores are deliberately NOT sent: the doctor sees them in the tiles beside this paragraph, and a model given "low scores" tends to
    # reassure. Less data leaves the server and the paragraph stays about what the person actually wrote.
    lines = [f"Person: age {age}" + (f", {u.gender}" if u.gender else "") + (f", {u.occupation}" if u.occupation else "") + "."]
    lines.append("Messages the person wrote to a support chat, oldest first:")
    lines += [f"- {m.text.strip()}" for m in _messages(db, u.id)]
    return "\n".join(lines)


_REASSURING = re.compile(
    r"\bno\s+(?:\w+\s+){0,2}(?:risks?|concerns?|risk\s+factors?|flags?|warning\s+signs?|red\s+flags?)\b"
    r"|\bscores?\s+(?:are|is|were|was)\s+(?:low|minimal|normal|fine)\b"
    r"|\bnothing\s+else\b|\bnot\s+(?:a\s+)?(?:concern|risk)\b|^not\s+stated\.?$",
    re.IGNORECASE,
)


def scrub(text: str) -> str:
    """Drop sentences that read as reassurance ("no other concerns are mentioned") or are empty filler ("Not stated."). The material may be incomplete,
    so a summary must only say what was written, never what was absent."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(x for x in sentences if x and not _REASSURING.search(x.strip())).strip()


def _source(db: Session, case: ConsultCase) -> list[str]:
    """The person's own message texts: what every quoted phrase must really come from."""
    return [m.text.strip() for m in _messages(db, case.user.id)]


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[\u2018\u2019]", "'", re.sub(r"[\u201c\u201d]", '"', t)).lower().split())


def validate(raw: dict, sources: list[str]) -> dict | None:
    """Keep only what is safe to show: short concern phrases with no reassurance, and quotes that really appear in the person's messages."""
    if not isinstance(raw, dict):
        return None
    hay = _norm(" \n ".join(sources))

    def short(x, limit):
        return isinstance(x, str) and 0 < len(x.strip()) <= limit and not _REASSURING.search(x) and not re.search(r"[\U0001F000-\U0001FFFF]", x)

    def verbatim(x):
        return isinstance(x, str) and 3 <= len(x.strip()) <= 300 and _norm(x.strip(' "\u201c\u201d')) in hay

    concerns = [c.strip().rstrip(".") for c in (raw.get("concerns") or []) if short(c, 80)][:4]
    how_long = raw.get("how_long") if short(raw.get("how_long"), 60) else None
    quote = raw.get("quote").strip(' "\u201c\u201d') if verbatim(raw.get("quote")) else None
    phrases = []
    for ph in raw.get("worrying_phrases") or []:
        if verbatim(ph) and ph.strip(' "\u201c\u201d') not in phrases:
            phrases.append(ph.strip(' "\u201c\u201d'))
    if not concerns and not quote:
        return None
    return {"concerns": concerns, "how_long": how_long.strip() if how_long else None, "quote": quote, "worrying_phrases": phrases[:4]}


def parse_overview(stored: str | None) -> dict | None:
    """The stored overview, or None if there is none or it is in an older free-text format (it is then prepared again)."""
    import json

    if not stored:
        return None
    try:
        data = json.loads(stored)
    except ValueError:
        return None
    return data if isinstance(data, dict) and "concerns" in data else None


def _extract_json(text: str) -> dict | None:
    import json

    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def draft_ai(db: Session, case: ConsultCase) -> str | None:
    """Ask the model for the structured overview and return it as validated JSON text, or None. Every quote is checked against the real messages."""
    import json

    if not (settings.llm_enabled and settings.groq_api_key):
        return None
    try:
        r = httpx.post(
            f"{settings.groq_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={"model": settings.groq_model, "temperature": 0.1, "max_tokens": 900, "reasoning_effort": "low",
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": payload_text(db, case)}]},
            timeout=max(settings.llm_timeout_seconds, 12.0),
        )
        r.raise_for_status()
        raw = _extract_json(r.json()["choices"][0]["message"]["content"] or "")
    except Exception:                                                    # noqa: BLE001 - any failure means "no AI overview"
        return None
    if raw is None:
        return None
    ok = validate(raw, _source(db, case))
    return json.dumps(ok) if ok else None


MAX_ATTEMPTS = 3
RETRY_AFTER_SECONDS = 45


def available() -> bool:
    return bool(settings.llm_enabled and settings.groq_api_key)


def wants_draft(case: ConsultCase) -> bool:
    """True when a draft should be prepared now: the person agreed, the model is configured, there is none yet, and we have not tried too often."""
    from datetime import datetime, timezone

    if not (case.ai_summary_consent and available()) or parse_overview(case.ai_summary):
        return False
    if (case.ai_summary_attempts or 0) >= MAX_ATTEMPTS:
        return False
    if case.ai_summary_tried_at is not None:
        tried = case.ai_summary_tried_at if case.ai_summary_tried_at.tzinfo else case.ai_summary_tried_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - tried).total_seconds() < RETRY_AFTER_SECONDS:
            return False
    return True


def is_pending(case: ConsultCase) -> bool:
    return bool(case.ai_summary_consent and available() and not parse_overview(case.ai_summary) and (case.ai_summary_attempts or 0) < MAX_ATTEMPTS)


def mark_attempt(db: Session, case: ConsultCase) -> None:
    from datetime import datetime, timezone

    case.ai_summary_attempts = (case.ai_summary_attempts or 0) + 1
    case.ai_summary_tried_at = datetime.now(timezone.utc)
    db.commit()


def run_in_background(bind, case_id: int) -> None:
    """Runs after the response has been sent. Uses its own session on the same database, never the request's."""
    from datetime import datetime, timezone

    from sqlalchemy.orm import sessionmaker

    from ..models import AuditLog

    with sessionmaker(bind=bind, expire_on_commit=False)() as db:
        case = db.get(ConsultCase, case_id)
        if case is None or parse_overview(case.ai_summary) or not case.ai_summary_consent:
            return
        text = draft_ai(db, case)
        actor = case.accepted_by or case.user_id
        db.add(AuditLog(actor_id=actor, action="ai_summary_ok" if text else "ai_summary_failed", target_type="consult", target_id=str(case_id)))
        if text:
            case.ai_summary = text
            case.ai_summary_at = datetime.now(timezone.utc)
        db.commit()
