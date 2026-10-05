from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import age_on, get_current_user, user_out
from ..models import Consent, User
from ..schemas import ConsentIn, LoginIn, RegisterIn, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])

# Constant-time-ish login: verify against a dummy hash when the user is unknown.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        settings.cookie_name,
        create_access_token(user_id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    age = age_on(body.date_of_birth)
    if age < 13 or age > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid date of birth. You must be at least 13.")
    minor = age < 18
    if minor and not (body.guardian_name and body.guardian_email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A parent or guardian's name and email are required.")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        date_of_birth=body.date_of_birth,
        gender=body.gender,
        occupation=body.occupation,
        language=body.language,
        phone=body.phone,
        emergency_contact=body.emergency_contact,
        guardian_name=body.guardian_name if minor else None,
        guardian_email=body.guardian_email if minor else None,
        guardian_consent_status="pending" if minor else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    _set_session(response, user.id)
    return user_out(db, user)


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    _set_session(response, user.id)
    return user_out(db, user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(settings.cookie_name, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_out(db, user)


@router.post("/consent", response_model=UserOut)
def accept_consent(body: ConsentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    if body.version != settings.consent_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "The consent text has changed. Reload and review it again.")
    db.add(Consent(user_id=user.id, version=body.version))
    db.commit()
    return user_out(db, user)
