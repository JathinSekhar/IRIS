import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# JSONB on Postgres (indexable, compact); plain JSON on SQLite for the test suite.
JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Application profile for a Supabase Auth user.

    Credentials live in Supabase's `auth.users`; this row shares its UUID. In Postgres the migration adds a foreign
    key to `auth.users(id)` with ON DELETE CASCADE. Passwords never reach this database.
    """

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | reviewer. Only the backend can write this.

    full_name: Mapped[str] = mapped_column(String(120))
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)

    guardian_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guardian_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    guardian_consent_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # pending | granted

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    consents: Mapped[list["Consent"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    checkins: Mapped[list["CheckIn"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(16))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="consents")


class CheckIn(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    questionnaire_version: Mapped[str] = mapped_column(String(16))
    answers: Mapped[dict] = mapped_column(JsonType, default=dict)
    scores: Mapped[dict] = mapped_column(JsonType, default=dict)
    baseline_risk: Mapped[str] = mapped_column(String(16), default="unknown")
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    free_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="checkins")


class AuditLog(Base):
    """Append-only record of reviewer access to sensitive data. No foreign keys, so entries outlive accounts."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(40))
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
