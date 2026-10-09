"""In-memory stand-in for Supabase Auth, with the same observable behaviour.

Used by the automated tests and by the local demo sandbox (`python -m devtools.demo_server`). It issues locally signed tokens, so
anything signed by it is worthless against a real deployment: the real service verifies Supabase's own asymmetric keys.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.auth_service import AuthError, Claims, Session, SignUpResult

TEST_SECRET = "test-signing-secret-at-least-32-bytes-long!!"


class FakeAuth:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.refresh_tokens: dict[str, str] = {}
        self.confirm_required = False
        self.recoveries: list[str] = []

    def _tokens(self, user_id: str, email: str, meta: dict, ttl: int = 3600) -> Session:
        now = datetime.now(timezone.utc)
        payload = {"sub": user_id, "email": email, "user_metadata": meta, "aud": "authenticated",
                   "iat": now, "exp": now + timedelta(seconds=ttl)}
        refresh = uuid.uuid4().hex
        self.refresh_tokens[refresh] = email
        return Session(jwt.encode(payload, TEST_SECRET, algorithm="HS256"), refresh, ttl)

    def sign_up(self, email, password, metadata, redirect_to):
        if email in self.users and not self.confirm_required:
            raise AuthError(409, "An account with this email already exists.")
        user = self.users.setdefault(email, {"id": str(uuid.uuid4()), "password": password, "meta": metadata,
                                             "confirmed": not self.confirm_required})
        session = None if self.confirm_required else self._tokens(user["id"], email, metadata)
        return SignUpResult(user["id"], session)

    def confirm(self, email):
        self.users[email]["confirmed"] = True

    def sign_in(self, email, password):
        u = self.users.get(email)
        if not u or u["password"] != password:
            raise AuthError(401, "Incorrect email or password.")
        if not u["confirmed"]:
            raise AuthError(403, "Please confirm your email first. Check your inbox for the link.")
        return self._tokens(u["id"], email, u["meta"])

    def refresh(self, refresh_token):
        email = self.refresh_tokens.pop(refresh_token, None)
        if email is None:
            raise AuthError(401, "Your session has expired. Please sign in again.")
        u = self.users[email]
        return self._tokens(u["id"], email, u["meta"])

    def sign_out(self, access_token):
        pass

    def recover(self, email, redirect_to):
        self.recoveries.append(email)

    def update_password(self, access_token, new_password):
        claims = self.verify(access_token)
        self.users[claims.email]["password"] = new_password

    def verify(self, access_token):
        try:
            p = jwt.decode(access_token, TEST_SECRET, algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError:
            raise AuthError(401, "Not signed in") from None
        return Claims(p["sub"], p["email"], p.get("user_metadata") or {})
