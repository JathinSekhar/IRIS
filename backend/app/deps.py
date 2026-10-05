from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import CheckIn, Consent, User
from .schemas import CheckinStatus, UserOut
from .security import decode_access_token


def age_on(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.cookie_name)
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


def require_reviewer(user: User = Depends(get_current_user)) -> User:
    if user.role != "reviewer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reviewer access required")
    return user


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def checkin_status(db: Session, user: User, now: datetime | None = None) -> CheckinStatus:
    now = now or datetime.now(timezone.utc)
    last_done = db.scalar(
        select(CheckIn).where(CheckIn.user_id == user.id, CheckIn.skipped.is_(False)).order_by(CheckIn.created_at.desc())
    )
    last_skip = db.scalar(
        select(CheckIn).where(CheckIn.user_id == user.id, CheckIn.skipped.is_(True)).order_by(CheckIn.created_at.desc())
    )
    done_at = _aware(last_done.created_at) if last_done else None
    due_at = done_at + timedelta(days=settings.checkin_valid_days) if done_at else None
    safety = last_done.safety_flag if last_done else False

    if due_at and due_at > now:
        return CheckinStatus(state="ok", last_completed_at=done_at, next_due_at=due_at, safety_flag=safety)

    state = "due" if last_done else "none"
    if last_skip:
        snooze_until = _aware(last_skip.created_at) + timedelta(hours=settings.checkin_skip_snooze_hours)
        if snooze_until > now:
            return CheckinStatus(
                state=state, last_completed_at=done_at, next_due_at=snooze_until, safety_flag=safety, prompt=False
            )
    return CheckinStatus(state=state, last_completed_at=done_at, next_due_at=due_at, safety_flag=safety, prompt=True)


def user_out(db: Session, user: User) -> UserOut:
    consented = db.scalar(
        select(Consent.id).where(Consent.user_id == user.id, Consent.version == settings.consent_version).limit(1)
    )
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        first_name=user.full_name.split()[0],
        role=user.role,
        is_minor=age_on(user.date_of_birth) < 18,
        guardian_consent_status=user.guardian_consent_status,
        consent_accepted=consented is not None,
        checkin=checkin_status(db, user),
    )
