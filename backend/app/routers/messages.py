from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_current_user, user_out
from ..models import CheckIn, Message, Prediction, User
from ..schemas import MessageIn, MessageOut, SupportReplyOut
from ..services import companion, triage

router = APIRouter(prefix="/api/messages", tags=["messages"])


def _out(m: Message) -> MessageOut:
    p = m.prediction
    cs = triage.care_status(p.status, p.first_opened_at)
    return MessageOut(id=m.id, text=m.text, created_at=m.created_at, reply=SupportReplyOut(**p.reply), care_status=cs,
                      status_text=triage.support.status_line(cs, p.message_urgent))


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send(body: MessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageOut:
    """Store the message, let the safety layers decide a provisional priority, queue it for a person, and return a supportive reply.

    Nothing here ever tells the person they are safe, and the response never contains a score or an urgency label.
    """
    if not user_out(db, user).consent_accepted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Consent is required before you can write to IRIS.")
    if len(body.text) > settings.message_max_chars:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That message is too long.")
    since = datetime.now(timezone.utc) - timedelta(minutes=1)
    recent = db.scalar(select(func.count()).select_from(Message).where(Message.user_id == user.id, Message.created_at > since))
    if recent >= settings.message_rate_limit_per_minute:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You are sending messages very quickly. Please wait a moment.")

    latest = db.scalar(
        select(CheckIn).where(CheckIn.user_id == user.id, CheckIn.skipped.is_(False)).order_by(CheckIn.created_at.desc(), CheckIn.id.desc())
    )
    floor, known = triage.baseline_floor(latest.scores if latest else None)
    result, plan = triage.run(body.text, floor)
    reply_json = {**triage.reply_json(plan), "companion": None}
    if companion.eligible(result, floor):
        earlier = db.scalars(select(Message).where(Message.user_id == user.id).order_by(Message.id.desc()).limit(companion.HISTORY_TURNS)).all()
        history = [(m.text, (m.prediction.reply or {}).get("companion")) for m in reversed(earlier) if m.prediction]
        said = companion.reply(body.text, history)
        if said:
            reply_json["companion"] = said

    msg = Message(user_id=user.id, text=body.text)
    msg.prediction = Prediction(
        model_version=triage.MODEL_VERSION, policy_version=triage.POLICY_VERSION,
        rule_level=result.rule_level, rule_hits=_hits(result.reasons), baseline_floor=floor, baseline_known=known,
        checkin_id=latest.id if latest else None, probabilities=None, model_urgency=result.model_urgency,
        initial_urgency=result.urgency, urgency=result.urgency, message_urgent=result.message_urgent, route=result.route, needs_human=True,
        risk_score=result.risk_score, reasons=list(result.reasons), reply=reply_json,
        reviewer_note=plan.reviewer_note, status=triage.PENDING,
    )
    db.add(msg)
    db.commit()
    return _out(msg)


def _hits(reasons: tuple[str, ...]) -> list[str]:
    """Rule names, parsed from the 'rule layer: <level> (a, b)' reason so reviewers can see which pattern fired."""
    for r in reasons:
        if r.startswith("rule layer:") and "(" in r:
            return [h.strip() for h in r[r.index("(") + 1 : r.rindex(")")].split(",")]
    return []


@router.get("", response_model=list[MessageOut])
def history(limit: int = Query(100, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[MessageOut]:
    """The signed-in person's own conversation, oldest first. Nobody else's messages are ever returned."""
    rows = db.scalars(select(Message).where(Message.user_id == user.id).order_by(Message.id.desc()).limit(limit)).all()
    return [_out(m) for m in reversed(rows)]
