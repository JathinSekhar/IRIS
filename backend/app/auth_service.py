"""Authentication provider boundary.

The app never stores or checks passwords. Supabase Auth (GoTrue) does sign-up, sign-in, email confirmation, password
reset and token refresh; this module wraps its REST API behind a small interface so the rest of the code (and the
tests) do not depend on Supabase directly.

Tokens are verified locally against the project's public JWKS (asymmetric ES256 signing), so no JWT secret is needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import jwt

from .config import settings


class AuthError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass
class SignUpResult:
    user_id: str
    session: Session | None  # None when the project requires email confirmation


@dataclass
class Claims:
    sub: str
    email: str
    user_metadata: dict[str, Any] = field(default_factory=dict)


class AuthService(Protocol):
    def sign_up(self, email: str, password: str, metadata: dict[str, Any], redirect_to: str) -> SignUpResult: ...
    def sign_in(self, email: str, password: str) -> Session: ...
    def refresh(self, refresh_token: str) -> Session: ...
    def sign_out(self, access_token: str) -> None: ...
    def recover(self, email: str, redirect_to: str) -> None: ...
    def update_password(self, access_token: str, new_password: str) -> None: ...
    def verify(self, access_token: str) -> Claims: ...


# GoTrue error_code -> (HTTP status, message shown to the user)
_ERRORS: dict[str, tuple[int, str]] = {
    "invalid_credentials": (401, "Incorrect email or password."),
    "email_not_confirmed": (403, "Please confirm your email first. Check your inbox for the link."),
    "user_already_exists": (409, "An account with this email already exists."),
    "email_exists": (409, "An account with this email already exists."),
    "weak_password": (422, "That password is too easy to guess. Try a longer or less common one."),
    "email_address_invalid": (422, "Enter a valid email address."),
    "validation_failed": (422, "Enter a valid email address and password."),
    "over_request_rate_limit": (429, "Too many attempts. Please wait a few minutes and try again."),
    "over_email_send_rate_limit": (429, "Too many emails sent. Please wait a few minutes and try again."),
    "same_password": (422, "Choose a password you have not used before."),
    "refresh_token_not_found": (401, "Your session has expired. Please sign in again."),
    "refresh_token_already_used": (401, "Your session has expired. Please sign in again."),
    "session_not_found": (401, "Your session has expired. Please sign in again."),
    "bad_jwt": (401, "This link has expired. Request a new one."),
}


class SupabaseAuth:
    def __init__(self, url: str, anon_key: str):
        if not url or not anon_key:
            raise AuthError(503, "Sign-in is not configured yet. Set IRIS_SUPABASE_URL and IRIS_SUPABASE_ANON_KEY.")
        self.base = url.rstrip("/") + "/auth/v1"
        self.issuer = self.base
        self._headers = {"apikey": anon_key, "Content-Type": "application/json"}
        self._http = httpx.Client(timeout=10.0)
        self._jwks = jwt.PyJWKClient(self.base + "/.well-known/jwks.json", cache_keys=True, lifespan=3600)

    # -- HTTP helper -------------------------------------------------------------------------------------------
    def _call(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None,
              token: str | None = None) -> dict:
        headers = dict(self._headers)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            res = self._http.request(method, self.base + path, json=json, params=params, headers=headers)
        except httpx.HTTPError:
            raise AuthError(503, "Can't reach the sign-in service. Please try again.") from None
        if res.status_code == 204 or not res.content:
            return {}
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.is_success:
            return data
        code = data.get("error_code") or data.get("code") or ""
        status, message = _ERRORS.get(str(code), (0, ""))
        if not status:
            status = res.status_code if res.status_code in (401, 403, 409, 422, 429) else 502
            message = "Something went wrong with the sign-in service. Please try again."
        raise AuthError(status, message)

    @staticmethod
    def _session(d: dict) -> Session:
        return Session(d["access_token"], d["refresh_token"], int(d.get("expires_in", 3600)))

    # -- AuthService ---------------------------------------------------------------------------------------------
    def sign_up(self, email: str, password: str, metadata: dict[str, Any], redirect_to: str) -> SignUpResult:
        d = self._call("POST", "/signup", json={"email": email, "password": password, "data": metadata},
                       params={"redirect_to": redirect_to})
        if "access_token" in d:
            return SignUpResult(d["user"]["id"], self._session(d))
        user_id = d.get("id") or d.get("user", {}).get("id") or ""
        return SignUpResult(user_id, None)

    def sign_in(self, email: str, password: str) -> Session:
        return self._session(
            self._call("POST", "/token", params={"grant_type": "password"}, json={"email": email, "password": password})
        )

    def refresh(self, refresh_token: str) -> Session:
        return self._session(
            self._call("POST", "/token", params={"grant_type": "refresh_token"}, json={"refresh_token": refresh_token})
        )

    def sign_out(self, access_token: str) -> None:
        try:
            self._call("POST", "/logout", token=access_token)
        except AuthError:
            pass  # best effort: the cookies are cleared regardless

    def recover(self, email: str, redirect_to: str) -> None:
        self._call("POST", "/recover", json={"email": email}, params={"redirect_to": redirect_to})

    def update_password(self, access_token: str, new_password: str) -> None:
        self._call("PUT", "/user", json={"password": new_password}, token=access_token)

    def verify(self, access_token: str) -> Claims:
        try:
            key = self._jwks.get_signing_key_from_jwt(access_token)
            payload = jwt.decode(
                access_token, key.key, algorithms=["ES256", "RS256"], audience="authenticated",
                issuer=self.issuer, leeway=10,
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError):
            raise AuthError(401, "Not signed in") from None
        return Claims(sub=payload["sub"], email=payload.get("email", ""), user_metadata=payload.get("user_metadata") or {})


_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """FastAPI dependency. Tests override it with an in-memory fake."""
    global _service
    if _service is None:
        _service = SupabaseAuth(settings.supabase_url, settings.supabase_anon_key)
    return _service
