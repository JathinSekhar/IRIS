from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..deps import age_on, require_reviewer
from ..models import AuditLog, CheckIn, Message, Prediction, Review, User
from ..schemas import (
    EscalateIn, ReviewEventOut, ReviewerCheckinOut, ReviewerCheckinSummary, ReviewerMessageOut, ReviewerMessageSummary, ReviewIn, SupportReplyOut,
    ThreadMessageOut, UrgentAlertsOut,
)
from ..services import triage

from iris_ml import URGENCY_INDEX, support  # noqa: E402  (importable once services.triage has put ml/ on the path)

router = APIRouter(prefix="/api/reviewer", tags=["reviewer"])

_RISK_ORDER = case(
    (CheckIn.escalated.is_(True), 0),
    (CheckIn.baseline_risk == "high", 1),
    (CheckIn.baseline_risk == "medium", 2),
    (CheckIn.baseline_risk == "low", 3),
    else_=4,
)


def _summary(c: CheckIn) -> ReviewerCheckinSummary:
    """Only what is needed to triage the queue. No answers, free text, contact details or scores."""
    return ReviewerCheckinSummary(
        id=c.id,
        user_name=c.user.full_name,
        created_at=c.created_at,
        baseline_risk=c.baseline_risk,
        safety_flag=c.safety_flag,
        escalated=c.escalated,
    )


def _detail(c: CheckIn) -> ReviewerCheckinOut:
    u = c.user
    return ReviewerCheckinOut(
        id=c.id,
        user_id=str(u.id),
        user_name=u.full_name,
        user_email=u.email,
        created_at=c.created_at,
        skipped=c.skipped,
        baseline_risk=c.baseline_risk,
        safety_flag=c.safety_flag,
        escalated=c.escalated,
        scores=c.scores,
        answers=c.answers,
        free_text=c.free_text,
        is_minor=age_on(u.date_of_birth) < 18,
        emergency_contact=u.emergency_contact,
        date_of_birth=u.date_of_birth,
    )


@router.get("/checkins", response_model=list[ReviewerCheckinSummary])
def list_checkins(
    limit: int = Query(50, ge=1, le=200),
    reviewer: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> list[ReviewerCheckinSummary]:
    rows = db.scalars(
        select(CheckIn)
        .options(joinedload(CheckIn.user))
        .where(CheckIn.skipped.is_(False))
        .order_by(_RISK_ORDER, CheckIn.created_at.desc())
        .limit(limit)
    ).all()
    db.add(AuditLog(actor_id=reviewer.id, action="list_queue", target_type="checkin", target_id=f"{len(rows)} rows"))
    db.commit()
    return [_summary(c) for c in rows]


@router.get("/checkins/{checkin_id}", response_model=ReviewerCheckinOut)
def get_checkin(
    checkin_id: int, reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)
) -> ReviewerCheckinOut:
    """Full clinical record. Every call is written to the audit log with the check-in and the person it belongs to."""
    row = db.scalar(select(CheckIn).options(joinedload(CheckIn.user)).where(CheckIn.id == checkin_id))
    if row is None:
        raise HTTPException(404, "Check-in not found")
    db.add(AuditLog(actor_id=reviewer.id, action="view_checkin", target_type="checkin", target_id=str(checkin_id)))
    db.commit()
    return _detail(row)


# --- messages (the chat): the human review queue ------------------------------------------------------------------------------------------------

_PRIORITY_ORDER = case((Prediction.urgency == "high", 0), (Prediction.urgency == "medium", 1), else_=2)
_PENDING_FIRST = case((Prediction.status == triage.PENDING, 0), else_=1)


def _message_summary(m: Message) -> ReviewerMessageSummary:
    p = m.prediction
    return ReviewerMessageSummary(
        id=m.id, user_name=m.user.full_name, created_at=m.created_at, priority=p.urgency, status=p.status,
        rule_flagged=p.rule_level != "none", reviewer_raised=any(r.kind == "escalation" for r in m.reviews), baseline_floor=p.baseline_floor,
        opened=p.first_opened_at is not None, urgent=p.message_urgent,
    )


def _message_detail(db: Session, m: Message) -> ReviewerMessageOut:
    p, u = m.prediction, m.user
    checkin = db.get(CheckIn, p.checkin_id) if p.checkin_id else None
    return ReviewerMessageOut(
        id=m.id, user_id=str(u.id), user_name=u.full_name, user_email=u.email, text=m.text, created_at=m.created_at,
        priority=p.urgency, initial_priority=p.initial_urgency, status=p.status, rule_level=p.rule_level, rule_hits=list(p.rule_hits or []),
        baseline_floor=p.baseline_floor, baseline_known=p.baseline_known, baseline_risk=checkin.baseline_risk if checkin else None,
        checkin_id=p.checkin_id, reasons=list(p.reasons or []), reviewer_note=p.reviewer_note, model_version=p.model_version,
        policy_version=p.policy_version, reply_shown=SupportReplyOut(**p.reply),
        history=[ReviewEventOut(id=r.id, kind=r.kind, from_urgency=r.from_urgency, to_urgency=r.to_urgency, notes=r.notes,
                                reviewer_name=r.reviewer_name, created_at=r.created_at) for r in m.reviews],
    )


def _load(db: Session, message_id: int) -> Message:
    m = db.scalar(select(Message).options(joinedload(Message.user), joinedload(Message.prediction), joinedload(Message.reviews)).where(Message.id == message_id))
    if m is None or m.prediction is None:
        raise HTTPException(404, "Message not found")
    return m


@router.get("/alerts", response_model=UrgentAlertsOut)
def alerts(reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> UrgentAlertsOut:
    """How many urgent messages are waiting, for an instant banner. Counts only (no names or text), so it is not audited and can be polled every few seconds."""
    rows = db.execute(
        select(Prediction.id, Prediction.message_id, Prediction.first_opened_at, Message.created_at)
        .join(Message, Message.id == Prediction.message_id)
        .where(Prediction.message_urgent.is_(True), Prediction.status == triage.PENDING).order_by(Message.created_at.asc())
    ).all()
    unopened = [r for r in rows if r.first_opened_at is None]
    now = datetime.now(timezone.utc)
    oldest = None
    if unopened:
        c = unopened[0].created_at
        oldest = max(0, int((now - (c if c.tzinfo else c.replace(tzinfo=timezone.utc))).total_seconds()))
    from sqlalchemy import func

    from ..models import ConsultCase
    from ..services import consult

    waiting = db.scalar(select(func.count()).select_from(ConsultCase).where(ConsultCase.state == consult.OPEN, ConsultCase.urgent.is_(True))) or 0
    open_cases = db.scalars(select(ConsultCase).where(ConsultCase.state == consult.OPEN)).all()
    overdue = sum(1 for c in open_cases if consult.waiting_long(c))
    return UrgentAlertsOut(urgent_waiting=len(rows), urgent_unopened=len(unopened), oldest_unopened_seconds=oldest,
                           latest_urgent_id=max((r.message_id for r in rows), default=None), doctor_requests_waiting=waiting,
                           doctor_requests_overdue=overdue)


@router.get("/messages", response_model=list[ReviewerMessageSummary])
def list_messages(limit: int = Query(100, ge=1, le=300), reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)):
    """Every message waits here for a person. Order: not yet reviewed first, then highest priority, then highest score, then oldest."""
    rows = db.scalars(
        select(Message).join(Prediction).options(joinedload(Message.user), joinedload(Message.prediction), joinedload(Message.reviews))
        .order_by(_PENDING_FIRST, _PRIORITY_ORDER, Prediction.risk_score.desc(), Message.created_at.asc()).limit(limit)
    ).unique().all()
    db.add(AuditLog(actor_id=reviewer.id, action="list_message_queue", target_type="message", target_id=f"{len(rows)} rows"))
    db.commit()
    return [_message_summary(m) for m in rows]


@router.get("/messages/{message_id}", response_model=ReviewerMessageOut)
def get_message(message_id: int, reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> ReviewerMessageOut:
    """The full message with what the safety layers decided and why. Every call is written to the audit log."""
    m = _load(db, message_id)
    if m.prediction.first_opened_at is None:
        m.prediction.first_opened_at = datetime.now(timezone.utc)      # the person's status line changes to "a person is reading this now"
    db.add(AuditLog(actor_id=reviewer.id, action="view_message", target_type="message", target_id=str(message_id)))
    db.commit()
    return _message_detail(db, m)


@router.post("/messages/{message_id}/escalate", response_model=ReviewerMessageOut)
def escalate_message(message_id: int, body: EscalateIn, reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> ReviewerMessageOut:
    """A reviewer raises a case to Medium or High (warning signs, a contradiction, or doubt). It can only raise, and it needs a reason."""
    m = _load(db, message_id)
    p = m.prediction
    if p.status != triage.PENDING:
        raise HTTPException(409, "This message has already been reviewed.")
    try:
        reason = support.validate_escalation(p.urgency, body.to, body.reason)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    before = p.urgency
    p.urgency = body.to
    p.route = "human_reviewer"
    p.risk_score = max(p.risk_score, float(URGENCY_INDEX[body.to]))
    p.reasons = list(p.reasons or []) + [support.ESCALATION_TEMPLATE.format(to=body.to, reason=reason)]
    if body.to == "high":
        p.message_urgent = True                                           # a reviewer who reads it and judges it High has made it urgent
    p.reviewer_note = triage.reviewer_note(p.urgency, p.risk_score, p.reasons, p.rule_level, p.baseline_floor, p.message_urgent)
    m.reviews.append(Review(reviewer_id=reviewer.id, reviewer_name=reviewer.full_name, kind="escalation", from_urgency=before, to_urgency=body.to, notes=reason))
    db.add(AuditLog(actor_id=reviewer.id, action="escalate_message", target_type="message", target_id=str(message_id)))
    db.commit()
    return _message_detail(db, m)


@router.post("/messages/{message_id}/review", response_model=ReviewerMessageOut)
def review_message(message_id: int, body: ReviewIn, reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> ReviewerMessageOut:
    """The reviewer's own judgement. This, and nothing automatic, is what moves a case out of the pending state."""
    m = _load(db, message_id)
    p = m.prediction
    if p.status != triage.PENDING:
        raise HTTPException(409, "This message has already been reviewed.")
    m.reviews.append(Review(reviewer_id=reviewer.id, reviewer_name=reviewer.full_name, kind="judgement", from_urgency=p.urgency, to_urgency=body.urgency, notes=body.notes.strip()))
    p.status = triage.REVIEWED
    db.add(AuditLog(actor_id=reviewer.id, action="review_message", target_type="message", target_id=str(message_id)))
    db.commit()
    return _message_detail(db, m)


@router.get("/consults/{case_id}/messages", response_model=list[ThreadMessageOut])
def consult_thread(case_id: int, reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> list[ThreadMessageOut]:
    """A reviewer can read a doctor conversation on request (for example after a complaint). Every read is written to the audit log."""
    from ..models import ConsultCase
    from ..services import consult

    if db.get(ConsultCase, case_id) is None:
        raise HTTPException(404, "Case not found")
    db.add(AuditLog(actor_id=reviewer.id, action="view_consult_thread", target_type="consult", target_id=str(case_id)))
    db.commit()
    return [ThreadMessageOut(id=m.id, sender_role=m.sender_role, mine=False, text=m.text, created_at=m.created_at, urgent=m.urgent)
            for m in consult.thread(db, case_id)]


@router.get("/consults/{case_id}/note")
def consult_note(case_id: int, reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> dict:
    """The doctor's session form for a case, on request. Every read is written to the audit log."""
    from ..models import SessionNote

    n = db.get(SessionNote, case_id)
    if n is None:
        raise HTTPException(404, "There is no session note for this case")
    db.add(AuditLog(actor_id=reviewer.id, action="view_session_note", target_type="consult", target_id=str(case_id)))
    db.commit()
    return {"case_id": n.case_id, "mode": n.mode, "concerns": n.concerns, "observations": n.observations, "ideation": n.ideation, "plan": n.plan,
            "intent": n.intent, "means_access": n.means_access, "previous_attempt": n.previous_attempt, "protective_factors": n.protective_factors,
            "risk_level": n.risk_level, "safety_plan": n.safety_plan, "safety_plan_copy_given": n.safety_plan_copy_given, "impression": n.impression,
            "actions_taken": n.actions_taken, "follow_up": n.follow_up, "follow_up_date": n.follow_up_date, "referral": n.referral,
            "emergency_services_contacted": n.emergency_services_contacted, "created_at": n.created_at}


@router.post("/messages/{message_id}/offer-doctor")
def offer_doctor(message_id: int, reviewer: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> dict:
    """Suggest a doctor to the person who wrote this message. Only an offer: the person decides, and nothing is shared unless they say yes."""
    from ..services import consult

    m = db.get(Message, message_id)
    if m is None:
        raise HTTPException(404, "Message not found")
    if consult.live_case(db, m.user_id) is not None:
        raise HTTPException(409, "This person already has a doctor request.")
    o = consult.make_offer(db, m.user_id, "reviewer", message_id=m.id, created_by=reviewer.id)
    return {"offered": o is not None, "reason": o.reason if o else None}
