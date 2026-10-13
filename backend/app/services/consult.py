"""Doctor requests: the honest status text, who may see a case, and the one-doctor-wins claim.

The rule that matters most: IRIS never tells the person a doctor is coming, or when, until a doctor has actually accepted. Before that the
status says it is trying, says it cannot say how long, and keeps the helplines in front of them. A test checks these lines for promises.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import CheckIn, ConsultCase, ConsultMessage, DoctorProfile, Message, User

OPEN, ACCEPTED, CLOSED, CANCELLED = "open", "accepted", "closed", "cancelled"
LIVE = (OPEN, ACCEPTED)

STATUS_TRYING = ("We are trying to reach a doctor for you. We cannot say how long this will take, so if you need someone right away, "
                 "please call one of the numbers below.")
STATUS_NONE_ON_DUTY = ("No doctor is available at the moment, and we cannot say when one might be. If you need someone right away, "
                       "please call one of the numbers below. Your request stays open.")
STATUS_ACCEPTED = "A doctor has accepted your request."
STATUS_CANCELLED = "You cancelled this request. You can ask again at any time."
STATUS_CLOSED = "This conversation has ended. You can ask again at any time."
SHARE_NOTICE = ("If you ask to talk to a doctor, the doctor who accepts can read your recent messages here and your check-in answers, "
                "so you do not have to repeat yourself. You can cancel your request at any time.")


def any_doctor_on_duty(db: Session) -> bool:
    return db.scalar(select(DoctorProfile.user_id).where(DoctorProfile.on_duty.is_(True)).limit(1)) is not None


def status_text(db: Session, case: ConsultCase) -> str:
    if case.state == ACCEPTED:
        return STATUS_ACCEPTED
    if case.state == CANCELLED:
        return STATUS_CANCELLED
    if case.state == CLOSED:
        return STATUS_CLOSED
    return STATUS_TRYING if any_doctor_on_duty(db) else STATUS_NONE_ON_DUTY


def live_case(db: Session, user_id) -> ConsultCase | None:
    return db.scalar(select(ConsultCase).where(ConsultCase.user_id == user_id, ConsultCase.state.in_(LIVE)).order_by(ConsultCase.id.desc()))


def claim(db: Session, case_id: int, doctor_id) -> bool:
    """Atomic: exactly one doctor wins. False means somebody else (or the person) got there first."""
    res = db.execute(
        update(ConsultCase).where(ConsultCase.id == case_id, ConsultCase.state == OPEN)
        .values(state=ACCEPTED, accepted_by=doctor_id, accepted_at=datetime.now(timezone.utc))
    )
    db.commit()
    return res.rowcount == 1


def summary_for_doctor(db: Session, case: ConsultCase) -> dict:
    """What a doctor sees before accepting: only because the person agreed to share it. Recent messages and the latest check-in's headline."""
    msgs = db.scalars(select(Message).where(Message.user_id == case.user_id).order_by(Message.id.desc()).limit(3)).all()
    latest = db.scalar(
        select(CheckIn).where(CheckIn.user_id == case.user_id, CheckIn.skipped.is_(False)).order_by(CheckIn.created_at.desc(), CheckIn.id.desc())
    )
    scores = (latest.scores if latest else None) or {}
    urgent = any(m.prediction and m.prediction.message_urgent for m in msgs)
    priorities = [m.prediction.urgency for m in msgs if m.prediction]
    rank = {"high": 0, "medium": 1, "low": 2}
    from ..deps import age_on

    return {
        "is_minor": age_on(case.user.date_of_birth) < 18,
        "urgent": urgent,
        "priority": min(priorities, key=lambda p: rank.get(p, 3)) if priorities else None,
        "recent_messages": [{"text": m.text, "created_at": m.created_at} for m in reversed(msgs)],
        "checkin": None if latest is None else {
            "baseline_risk": latest.baseline_risk, "safety_flag": latest.safety_flag,
            "phq9": (scores.get("phq9") or {}).get("score"), "gad7": (scores.get("gad7") or {}).get("score"),
            "created_at": latest.created_at,
        },
    }


def person_first_name(user: User) -> str:
    return user.full_name.split()[0]


THREAD_MAX_CHARS = 2000
THREAD_RATE_PER_MINUTE = 30


def thread(db: Session, case_id: int) -> list[ConsultMessage]:
    return list(db.scalars(select(ConsultMessage).where(ConsultMessage.case_id == case_id).order_by(ConsultMessage.id)).all())


def too_fast(db: Session, case_id: int, sender_id) -> bool:
    from datetime import timedelta

    from sqlalchemy import func

    since = datetime.now(timezone.utc) - timedelta(minutes=1)
    n = db.scalar(select(func.count()).select_from(ConsultMessage).where(
        ConsultMessage.case_id == case_id, ConsultMessage.sender_id == sender_id, ConsultMessage.created_at > since))
    return (n or 0) >= THREAD_RATE_PER_MINUTE


def add_message(db: Session, case: ConsultCase, sender: User, role: str, text: str) -> ConsultMessage:
    """Store one message. A person's line is scanned by the rule layer so the doctor sees a flag on a worrying one; a doctor's is stored as written."""
    from . import triage

    urgent = role == "user" and triage.run(text, "none")[0].rule_level != "none"
    m = ConsultMessage(case_id=case.id, sender_id=sender.id, sender_role=role, text=text, urgent=urgent)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m
