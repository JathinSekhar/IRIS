"""Doctor requests: the honest status text, who may see a case, and the one-doctor-wins claim.

The rule that matters most: IRIS never tells the person a doctor is coming, or when, until a doctor has actually accepted. Before that the
status says it is trying, says it cannot say how long, and keeps the helplines in front of them. A test checks these lines for promises.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import CheckIn, ConsultCase, ConsultMessage, DoctorProfile, Message, User

OPEN, ACCEPTED, IN_SESSION, CLOSED, CANCELLED = "open", "accepted", "in_session", "closed", "cancelled"
# accepted = a doctor took the case and has not begun yet; in_session = the doctor started the conversation (chat and video open).
LIVE = (OPEN, ACCEPTED, IN_SESSION)
WITH_DOCTOR = (ACCEPTED, IN_SESSION)

STATUS_TRYING = ("We are trying to reach a doctor for you. We cannot say how long this will take, so if you need someone right away, "
                 "please call one of the numbers below.")
STATUS_NONE_ON_DUTY = ("No doctor is available at the moment, and we cannot say when one might be. If you need someone right away, "
                       "please call one of the numbers below. Your request stays open.")
STATUS_WAITING_LONG = ("No doctor has been able to accept your request yet. We are still trying, but we cannot say when one will. "
                       "If you need someone now, please call one of the numbers below. You can keep your request open or cancel it.")
STATUS_ACCEPTED = "A doctor has accepted your request. The conversation will begin when they are ready."
STATUS_IN_SESSION = "Your doctor has started the conversation."
STATUS_CANCELLED = "You cancelled this request. You can ask again at any time."
STATUS_CLOSED = "This conversation has ended. You can ask again at any time."
SHARE_NOTICE = ("If you ask to talk to a doctor, the doctor who accepts can read your recent messages here and your check-in answers, "
                "so you do not have to repeat yourself. You can cancel your request at any time.")


def any_doctor_on_duty(db: Session) -> bool:
    return db.scalar(select(DoctorProfile.user_id).where(DoctorProfile.on_duty.is_(True)).limit(1)) is not None


def status_text(db: Session, case: ConsultCase) -> str:
    if case.state == ACCEPTED:
        return STATUS_ACCEPTED
    if case.state == IN_SESSION:
        return STATUS_IN_SESSION
    if case.state == CANCELLED:
        return STATUS_CANCELLED
    if case.state == CLOSED:
        return STATUS_CLOSED
    if waiting_long(case):
        return STATUS_WAITING_LONG
    return STATUS_TRYING if any_doctor_on_duty(db) else STATUS_NONE_ON_DUTY


def waiting_minutes(case: ConsultCase) -> int:
    created = case.created_at if case.created_at.tzinfo else case.created_at.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - created).total_seconds() // 60))


def waiting_long(case: ConsultCase) -> bool:
    """An open request nobody has accepted within the team's goal. The goal is never shown to the person."""
    from ..config import settings

    return case.state == OPEN and waiting_minutes(case) >= settings.doctor_wait_goal_minutes


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

    flag = None
    if role == "user":
        r = triage.run(text, "none")[0]
        flag = "urgent" if r.message_urgent else ("worrying" if r.rule_level != "none" else None)
    m = ConsultMessage(case_id=case.id, sender_id=sender.id, sender_role=role, text=text, urgent=flag is not None, flag=flag)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


# ---- video call set-up (signalling only) --------------------------------------------------------------------------------------------------------
SIGNAL_RATE_PER_MINUTE = 240
RTC_KINDS = ("offer", "answer", "ice")


def add_signal(db: Session, case: ConsultCase, role: str, kind: str, payload: dict | None):
    """Store one set-up message. A new request starts clean; an end or decline wipes the set-up data (it holds network addresses) and keeps only
    itself so the other side learns the call is over. An accept marks the case as having used video."""
    from sqlalchemy import delete

    from ..models import ConsultSignal

    if kind == "request":
        db.execute(delete(ConsultSignal).where(ConsultSignal.case_id == case.id))
    if kind in ("end", "decline"):
        db.execute(delete(ConsultSignal).where(ConsultSignal.case_id == case.id))
    if kind == "accept":
        case.video_used = True
    sig = ConsultSignal(case_id=case.id, sender_role=role, kind=kind, payload=payload)
    db.add(sig)
    db.commit()
    db.refresh(sig)
    return sig


def signals_for(db: Session, case_id: int, viewer_role: str, after: int = 0):
    """What the other side sent, after id `after`. Your own messages are not echoed back."""
    from ..models import ConsultSignal

    return list(db.scalars(
        select(ConsultSignal).where(ConsultSignal.case_id == case_id, ConsultSignal.id > after, ConsultSignal.sender_role != viewer_role)
        .order_by(ConsultSignal.id)
    ).all())


def signals_too_fast(db: Session, case_id: int, role: str) -> bool:
    from datetime import timedelta

    from sqlalchemy import func

    from ..models import ConsultSignal

    since = datetime.now(timezone.utc) - timedelta(minutes=1)
    n = db.scalar(select(func.count()).select_from(ConsultSignal).where(
        ConsultSignal.case_id == case_id, ConsultSignal.sender_role == role, ConsultSignal.created_at > since))
    return (n or 0) >= SIGNAL_RATE_PER_MINUTE


# ---- offering a doctor (step 6) ------------------------------------------------------------------------------------------------------------------
# The person always chooses. These lines never promise a doctor or a time; a test checks them.
OFFER_TEXT = {
    "urgent_message": ("Would you like to talk to a doctor now?",
                       "A doctor on the IRIS team can talk with you here. They may not be able to answer straight away, so the numbers above are still "
                       "the quickest way to reach someone."),
    "high_checkin": ("Would you like to talk to a doctor?",
                     "From your check-in answers, it may help to talk with a doctor on the IRIS team. They may not be able to answer straight away, "
                     "and the helplines are always there."),
    "reviewer": ("Would you like to talk to a doctor?",
                 "Someone on our team who read your messages thinks it may help to talk with a doctor. It is your choice, and they may not be able "
                 "to answer straight away."),
}
URGENT_REASONS = ("urgent_message", "high_checkin")


def open_offer(db: Session, user_id):
    from ..models import DoctorOffer

    return db.scalar(select(DoctorOffer).where(DoctorOffer.user_id == user_id, DoctorOffer.resolved_at.is_(None)).order_by(DoctorOffer.id.desc()))


def make_offer(db: Session, user_id, reason: str, message_id: int | None = None, created_by=None):
    """Create an offer unless the person already has a live doctor request or an unanswered offer. Returns the offer that is now showing, or None."""
    from ..models import AuditLog, DoctorOffer

    if live_case(db, user_id) is not None:
        return None
    existing = open_offer(db, user_id)
    if existing is not None:
        return existing
    o = DoctorOffer(user_id=user_id, reason=reason, message_id=message_id, created_by=created_by)
    db.add(o)
    db.add(AuditLog(actor_id=created_by or user_id, action=f"offer_doctor_{reason}", target_type="user", target_id=str(user_id)))
    db.commit()
    db.refresh(o)
    return o


def resolve_offers(db: Session, user_id, resolution: str) -> None:
    from ..models import DoctorOffer

    now = datetime.now(timezone.utc)
    for o in db.scalars(select(DoctorOffer).where(DoctorOffer.user_id == user_id, DoctorOffer.resolved_at.is_(None))).all():
        o.resolved_at, o.resolution = now, resolution
    db.commit()


def urgent_reason_for(db: Session, user_id) -> str | None:
    """Why a request from this person should be marked urgent: an explicit message in the last day, or a High floor from their latest check-in."""
    from datetime import timedelta

    from ..models import Prediction

    since = datetime.now(timezone.utc) - timedelta(days=1)
    explicit = db.scalar(
        select(Message.id).join(Prediction, Prediction.message_id == Message.id)
        .where(Message.user_id == user_id, Message.created_at > since, Prediction.message_urgent.is_(True)).limit(1)
    )
    if explicit is not None:
        return "urgent_message"
    latest = db.scalar(select(CheckIn).where(CheckIn.user_id == user_id, CheckIn.skipped.is_(False)).order_by(CheckIn.created_at.desc(), CheckIn.id.desc()))
    if latest is not None and ((latest.scores or {}).get("safety") or {}).get("urgency_floor") == "high":
        return "high_checkin"
    return None
