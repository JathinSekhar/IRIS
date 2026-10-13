import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Uuid
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


class ConsultCase(Base):
    """A person's request to talk to a doctor. It is OPEN to every on-duty doctor until one accepts, and the first to accept owns it.

    states: open -> accepted -> (closed, later steps) | cancelled. `source` says who started it: user | system | reviewer.
    The person must agree to share their recent messages and check-in answers before the case exists (`share_consent`).
    """

    __tablename__ = "consult_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(16), default="open", index=True)
    source: Mapped[str] = mapped_column(String(16), default="user")
    share_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    video_used: Mapped[bool] = mapped_column(Boolean, default=False)         # a video call was accepted during this case
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)    # the doctor began the conversation
    # Optional, separate agreement: an AI tool may draft a short summary for the doctor. Nothing is sent to it without this.
    ai_summary_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_summary_attempts: Mapped[int] = mapped_column(Integer, default=0)       # background tries so far; stops after a few so a failing model is not hammered
    ai_summary_tried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    doctor: Mapped[User | None] = relationship(foreign_keys=[accepted_by])


class ConsultDecline(Base):
    """A doctor passed on a case; it is not shown to them again. Other doctors still see it."""

    __tablename__ = "consult_declines"

    case_id: Mapped[int] = mapped_column(ForeignKey("consult_cases.id", ondelete="CASCADE"), primary_key=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    declined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsultMessage(Base):
    """One message in the conversation between a person and the doctor who accepted their case. Sensitive: only those two (and a reviewer, audited) can read it.

    `urgent` is a flag from the same rule layer that scans chat messages; it is shown to the doctor so a worrying line is not missed. It never changes
    what the person sees, and nothing here is written by a model.
    """

    __tablename__ = "consult_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("consult_cases.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    sender_role: Mapped[str] = mapped_column(String(8))                     # user | doctor
    text: Mapped[str] = mapped_column(Text)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ConsultSignal(Base):
    """Set-up messages for a video call (request, accept, decline, end, offer, answer, ice). Never media. The WebRTC payloads contain network addresses, so
    they are deleted as soon as a call ends or is declined; only the final end/decline event is kept so the other side learns about it."""

    __tablename__ = "consult_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("consult_cases.id", ondelete="CASCADE"), index=True)
    sender_role: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionNote(Base):
    """The documented session form a doctor must complete to end a conversation. Clinical record: never shown to the person; a reviewer can read
    it on request (audited). One per case."""

    __tablename__ = "session_notes"

    case_id: Mapped[int] = mapped_column(ForeignKey("consult_cases.id", ondelete="CASCADE"), primary_key=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(8))                              # chat | video | both
    concerns: Mapped[str] = mapped_column(Text)
    # Structured suicide-risk questions, each answered explicitly: yes | no | not_assessed. "not_assessed" is a real answer, not a blank.
    ideation: Mapped[str] = mapped_column(String(12))
    plan: Mapped[str] = mapped_column(String(12))
    intent: Mapped[str] = mapped_column(String(12))
    means_access: Mapped[str] = mapped_column(String(12))
    previous_attempt: Mapped[str] = mapped_column(String(12))
    protective_factors: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(8))                        # low | medium | high: the doctor's overall judgement
    safety_plan: Mapped[str] = mapped_column(String(12))                      # not_needed | created | updated | reviewed
    safety_plan_copy_given: Mapped[bool] = mapped_column(Boolean, default=False)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)     # what the doctor observed, kept apart from what the person reported
    impression: Mapped[str | None] = mapped_column(Text, nullable=True)       # clinical impression in the doctor's words; IRIS itself does not diagnose
    actions_taken: Mapped[str] = mapped_column(Text)
    follow_up: Mapped[str] = mapped_column(Text)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    referral: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_services_contacted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
