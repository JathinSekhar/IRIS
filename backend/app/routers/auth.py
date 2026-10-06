from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..auth_service import AuthError, AuthService, Session as AuthSession, get_auth_service
from ..config import settings
from ..db import get_db
from ..deps import age_on, get_current_user, get_or_create_user, user_out
from ..models import Consent, User
from ..schemas import ConsentIn, ForgotIn, LoginIn, RegisterIn, RegisterOut, ResetIn, UserOut

router = APIRouter(prefix="/api", tags=["auth"])

REFRESH_PATH = "/api/auth"


def _set_cookies(response: Response, session: AuthSession) -> None:
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(settings.access_cookie, session.access_token, max_age=session.expires_in, path="/", **common)
    response.set_cookie(
        settings.refresh_cookie, session.refresh_token, max_age=settings.refresh_cookie_days * 86400,
        path=REFRESH_PATH, **common,
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(settings.access_cookie, path="/")
    response.delete_cookie(settings.refresh_cookie, path=REFRESH_PATH)


def _http(e: AuthError) -> HTTPException:
    return HTTPException(e.status_code, e.message)


@router.post("/auth/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterIn, response: Response, db: Session = Depends(get_db), auth: AuthService = Depends(get_auth_service)
) -> RegisterOut:
    age = age_on(body.date_of_birth)
    if age < 13 or age > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid date of birth. You must be at least 13.")
    if age < 18 and not (body.guardian_name and body.guardian_email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A parent or guardian's name and email are required.")

    metadata = body.model_dump(mode="json", exclude={"email", "password"}, exclude_none=True)
    try:
        result = auth.sign_up(body.email, body.password, metadata, f"{settings.site_url}/login?confirmed=1")
    except AuthError as e:
        raise _http(e) from None

    if result.session is None:  # email confirmation required: the profile is created at first sign-in
        return RegisterOut(confirm_email=True)
    _set_cookies(response, result.session)
    claims = auth.verify(result.session.access_token)
    return RegisterOut(confirm_email=False, user=user_out(db, get_or_create_user(db, claims)))


@router.post("/auth/login", response_model=UserOut)
def login(
    body: LoginIn, response: Response, db: Session = Depends(get_db), auth: AuthService = Depends(get_auth_service)
) -> UserOut:
    try:
        session = auth.sign_in(body.email, body.password)
        claims = auth.verify(session.access_token)
    except AuthError as e:
        raise _http(e) from None
    user = get_or_create_user(db, claims)
    _set_cookies(response, session)
    return user_out(db, user)


@router.post("/auth/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(request: Request, response: Response, auth: AuthService = Depends(get_auth_service)) -> None:
    token = request.cookies.get(settings.refresh_cookie)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        session = auth.refresh(token)
    except AuthError as e:
        _clear_cookies(response)
        raise _http(e) from None
    _set_cookies(response, session)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, auth: AuthService = Depends(get_auth_service)) -> None:
    token = request.cookies.get(settings.access_cookie)
    if token:
        auth.sign_out(token)  # revokes the refresh token at Supabase; best effort
    _clear_cookies(response)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_out(db, user)


@router.post("/auth/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(body: ForgotIn, auth: AuthService = Depends(get_auth_service)) -> None:
    """Always answers 204 so the endpoint cannot be used to discover which emails have accounts."""
    try:
        auth.recover(body.email, f"{settings.site_url}/reset-password")
    except AuthError as e:
        if e.status_code == 429:
            raise _http(e) from None


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetIn, auth: AuthService = Depends(get_auth_service)) -> None:
    try:
        auth.update_password(body.access_token, body.password)
    except AuthError as e:
        raise _http(e) from None


@router.post("/consent", response_model=UserOut)
def accept_consent(body: ConsentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    if body.version != settings.consent_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "The consent text has changed. Reload and review it again.")
    db.add(Consent(user_id=user.id, version=body.version))
    db.commit()
    return user_out(db, user)
