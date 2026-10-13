import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_service import AuthError, AuthService, Claims, get_auth_service
from .config import settings
from .db import get_db
from .models import CheckIn, Consent, User
from .schemas import CheckinStatus, ProfileMeta, UserOut


def age_on(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _create_profile(db: Session, claims: Claims) -> User:
    """First authenticated request after sign-up: build the profile from the metadata stored with the auth user.

    Doing this lazily (instead of right after sign-up) means there is never an auth account without a profile, even
    if the database was unavailable during sign-up, and it works unchanged when email confirmation is required.
    The metadata is re-validated because Supabase sign-up is callable directly with the public anon key.
    """
    try:
        meta = ProfileMeta.model_validate(claims.user_metadata)
    except ValidationError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your profile is incomplete. Please contact support.") from None
    age = age_on(meta.date_of_birth)
    minor = age < 18
    if age < 13 or age > 100 or (minor and not (meta.guardian_name and meta.guardian_email)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your profile is incomplete. Please contact support.")
    user = User(
        id=uuid.UUID(claims.sub),
        email=claims.email.lower(),
        role="user",  # never taken from user-editable metadata
        full_name=meta.full_name.strip(),
        date_of_birth=meta.date_of_birth,
        gender=meta.gender,
        occupation=meta.occupation,
        language=meta.language,
        phone=meta.phone,
        emergency_contact=meta.emergency_contact,
        guardian_name=meta.guardian_name if minor else None,
        guardian_email=meta.guardian_email if minor else None,
        guardian_consent_status="pending" if minor else None,
    )
    db.add(user)
    db.commit()
    return user


def get_or_create_user(db: Session, claims: Claims) -> User:
    user = db.get(User, uuid.UUID(claims.sub))
    return user if user is not None else _create_profile(db, claims)


def get_current_user(
    request: Request, db: Session = Depends(get_db), auth: AuthService = Depends(get_auth_service)
) -> User:
    token = request.cookies.get(settings.access_cookie)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        claims = auth.verify(token)
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in") from None
    return get_or_create_user(db, claims)


def require_reviewer(user: User = Depends(get_current_user)) -> User:
    if user.role != "reviewer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reviewer access required")
    return user


def require_doctor(user: User = Depends(get_current_user)) -> User:
    if user.role != "doctor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctor access required")
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
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        first_name=user.full_name.split()[0],
        role=user.role,
        is_minor=age_on(user.date_of_birth) < 18,
        guardian_consent_status=user.guardian_consent_status,
        consent_accepted=consented is not None,
        checkin=checkin_status(db, user),
    )
