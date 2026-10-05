from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..deps import age_on, require_reviewer
from ..models import CheckIn, User
from ..schemas import ReviewerCheckinOut

router = APIRouter(prefix="/api/reviewer", tags=["reviewer"])

_RISK_ORDER = case(
    (CheckIn.escalated.is_(True), 0),
    (CheckIn.baseline_risk == "high", 1),
    (CheckIn.baseline_risk == "medium", 2),
    (CheckIn.baseline_risk == "low", 3),
    else_=4,
)


def _out(c: CheckIn) -> ReviewerCheckinOut:
    u = c.user
    return ReviewerCheckinOut(
        id=c.id,
        user_id=u.id,
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


@router.get("/checkins", response_model=list[ReviewerCheckinOut])
def list_checkins(
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> list[ReviewerCheckinOut]:
    rows = db.scalars(
        select(CheckIn)
        .options(joinedload(CheckIn.user))
        .where(CheckIn.skipped.is_(False))
        .order_by(_RISK_ORDER, CheckIn.created_at.desc())
        .limit(limit)
    ).all()
    return [_out(c) for c in rows]


@router.get("/checkins/{checkin_id}", response_model=ReviewerCheckinOut)
def get_checkin(checkin_id: int, _: User = Depends(require_reviewer), db: Session = Depends(get_db)) -> ReviewerCheckinOut:
    row = db.scalar(select(CheckIn).options(joinedload(CheckIn.user)).where(CheckIn.id == checkin_id))
    if row is None:
        raise HTTPException(404, "Check-in not found")
    return _out(row)
