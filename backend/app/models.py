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
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | reviewer | doctor. Only the backend can write this.

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


class DoctorProfile(Base):
    """A clinician who can be offered cases. The account itself is a `profiles` row with role 'doctor'; this holds what a doctor adds.

    `on_duty` is the doctor's own switch: cases are offered only to doctors who are on duty. The registration number is stored as given and is NOT
    verified by IRIS; real use needs a verification step outside this app.
    """

    __tablename__ = "doctor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    specialty: Mapped[str] = mapped_column(String(80))
    registration_number: Mapped[str] = mapped_column(String(64))
    languages: Mapped[list] = mapped_column(JsonType, default=list)
    on_duty: Mapped[bool] = mapped_column(Boolean, default=False)
    on_duty_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()


class AuditLog(Base):
    """Append-only record of reviewer access to sensitive data. No foreign keys, so entries outlive accounts."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(40))
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Message(Base):
    """A message the person typed to IRIS. Sensitive: only the owner and reviewers (audited) can read it; the browser never queries this table."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship()
    prediction: Mapped["Prediction"] = relationship(back_populates="message", uselist=False, cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="message", cascade="all, delete-orphan", order_by="Review.id")


class Prediction(Base):
    """What the safety layers decided for a message. `urgency` is a PROVISIONAL priority for the reviewer, never a cleared decision, and every row
    starts as `pending_human_review`. Nothing here is shown to the person."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), unique=True)
    model_version: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[str] = mapped_column(String(40))
    rule_level: Mapped[str] = mapped_column(String(16))          # none | review | high
    rule_hits: Mapped[list] = mapped_column(JsonType, default=list)
    baseline_floor: Mapped[str] = mapped_column(String(16))      # none | medium | high
    baseline_known: Mapped[bool] = mapped_column(Boolean, default=False)
    checkin_id: Mapped[int | None] = mapped_column(ForeignKey("checkins.id", ondelete="SET NULL"), nullable=True)
    probabilities: Mapped[list | None] = mapped_column(JsonType, nullable=True)   # null while no model is used
    model_urgency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    initial_urgency: Mapped[str] = mapped_column(String(16))
    urgency: Mapped[str] = mapped_column(String(16), index=True)  # current priority (a reviewer can raise it)
    route: Mapped[str] = mapped_column(String(24))
    needs_human: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_score: Mapped[float] = mapped_column(default=0.0)
    reasons: Mapped[list] = mapped_column(JsonType, default=list)
    reply: Mapped[dict] = mapped_column(JsonType, default=dict)  # exactly what the person was shown
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="pending_human_review", index=True)
    # True when the MESSAGE itself is urgent (explicit intent/plan/means, an explicit statement about ending one's life, or a reviewer raised it to High). A High that comes
    # only from the check-in floor leaves this False: the case is still High in the queue, but it is not an instant alert and the person is not alarmed by a calm message.
    message_urgent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)   # when a reviewer first opened it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    message: Mapped[Message] = relationship(back_populates="prediction")


class Review(Base):
    """A reviewer's action on a message: raising its priority, or recording their own judgement. Append-only history."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)       # no foreign key, like the audit log: history outlives accounts
    reviewer_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))                           # escalation | judgement
    from_urgency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_urgency: Mapped[str] = mapped_column(String(16))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped[Message] = relationship(back_populates="reviews")
