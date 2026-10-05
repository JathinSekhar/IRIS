from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | reviewer

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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(16))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="consents")


class CheckIn(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    questionnaire_version: Mapped[str] = mapped_column(String(16))
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_risk: Mapped[str] = mapped_column(String(16), default="unknown")
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    free_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="checkins")
