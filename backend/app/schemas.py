from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .services.questionnaire import Answer


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    date_of_birth: date
    gender: str | None = Field(default=None, max_length=32)
    occupation: str | None = Field(default=None, max_length=32)
    language: str = Field(default="en", max_length=16)
    phone: str | None = Field(default=None, max_length=32)
    emergency_contact: str | None = Field(default=None, max_length=200)
    guardian_name: str | None = Field(default=None, max_length=120)
    guardian_email: EmailStr | None = None

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class ProfileMeta(BaseModel):
    """Profile fields carried in Supabase `user_metadata`. Re-validated on the server, because the anon key is
    public and anyone can call Supabase sign-up directly with arbitrary metadata."""

    full_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date
    gender: str | None = Field(default=None, max_length=32)
    occupation: str | None = Field(default=None, max_length=32)
    language: str = Field(default="en", max_length=16)
    phone: str | None = Field(default=None, max_length=32)
    emergency_contact: str | None = Field(default=None, max_length=200)
    guardian_name: str | None = Field(default=None, max_length=120)
    guardian_email: str | None = Field(default=None, max_length=254)


class RegisterOut(BaseModel):
    confirm_email: bool          # True when the project requires email confirmation before sign-in
    user: "UserOut | None" = None


class ForgotIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class ResetIn(BaseModel):
    access_token: str = Field(min_length=10, max_length=4096)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class CheckinStatus(BaseModel):
    state: Literal["none", "due", "ok"]
    last_completed_at: datetime | None = None
    next_due_at: datetime | None = None
    safety_flag: bool = False
    prompt: bool = False  # should the app send the user to the check-in now?


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    first_name: str
    role: str
    is_minor: bool
    guardian_consent_status: str | None
    consent_accepted: bool
    checkin: CheckinStatus


class ConsentIn(BaseModel):
    version: str


class CheckinIn(BaseModel):
    answers: dict[str, Answer] = {}
    skipped: bool = False


class CheckinOut(BaseModel):
    """What the end user gets back. Deliberately contains no scores or risk labels."""
    id: int
    skipped: bool
    safety_flag: bool
    show_crisis_resources: bool
    created_at: datetime


class ReviewerCheckinSummary(BaseModel):
    """One row of the review queue: enough to triage, nothing more."""
    id: int
    user_name: str
    created_at: datetime
    baseline_risk: str
    safety_flag: bool
    escalated: bool


class ReviewerCheckinOut(BaseModel):
    id: int
    user_id: str
    user_name: str
    user_email: str
    created_at: datetime
    skipped: bool
    baseline_risk: str
    safety_flag: bool
    escalated: bool
    scores: dict
    answers: dict
    free_text: str | None
    is_minor: bool
    emergency_contact: str | None
    date_of_birth: date


RegisterOut.model_rebuild()


# --- messages (the chat) and the reviewer's view of them ---------------------------------------------------------------------------------

class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Write a message first")
        return v.strip()


class ReplyItem(BaseModel):
    title: str
    how: str


class HelplineOut(BaseModel):
    name: str
    detail: str
    number: str
    tel: str


class SupportReplyOut(BaseModel):
    """Everything the person may see. No urgency label, score, topic code or reason: a test enforces it."""

    layout: str = "tips"                      # how to present it (tips | celebrate | support | help_now); presentation only
    helplines: list[HelplineOut] = []         # tap-to-call cards; empty unless a safety layer fired
    intro: str
    listening: str
    self_help: list[ReplyItem]
    reach_out: list[str]
    crisis_lead: str
    crisis_lines: list[str]
    show_crisis_resources: bool
    emergency_footer: str
    closing: str
    a_person_may_reach_out: bool
    companion: str | None = None              # an AI-written conversational line, only for ordinary messages; replaces intro+listening when present


class DoctorMeOut(BaseModel):
    full_name: str
    specialty: str
    registration_number: str
    languages: list[str]
    on_duty: bool
    on_duty_changed_at: datetime | None = None


class DoctorAvailabilityIn(BaseModel):
    on_duty: bool


class ConsultRequestIn(BaseModel):
    share: bool                               # the person agreed to share recent messages and check-in answers with the doctor who accepts


class ConsultOut(BaseModel):
    id: int
    state: str                                # open | accepted | closed | cancelled
    status_text: str                          # the honest sentence for this state; never promises a doctor or a time before one accepts
    created_at: datetime
    doctor_name: str | None = None            # only once a doctor has accepted
    doctor_specialty: str | None = None
    doctor_registration_number: str | None = None   # shown to the person once a doctor has accepted, as the guidelines expect
    helplines: list[HelplineOut] = []         # always present, so the numbers are in front of them while they wait


class OfferMessageOut(BaseModel):
    text: str
    created_at: datetime


class OfferCheckinOut(BaseModel):
    baseline_risk: str
    safety_flag: bool
    phq9: int | None = None
    gad7: int | None = None
    created_at: datetime


class OfferOut(BaseModel):
    case_id: int
    first_name: str
    created_at: datetime
    source: str
    urgent: bool
    priority: str | None = None
    is_minor: bool = False
    recent_messages: list[OfferMessageOut]
    checkin: OfferCheckinOut | None = None


class ThreadMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Write a message first.")
        return v


class ThreadMessageOut(BaseModel):
    id: int
    sender_role: str                          # user | doctor
    mine: bool                                # true when the signed-in person wrote it
    text: str
    created_at: datetime
    urgent: bool = False                      # only ever true in what a doctor or reviewer sees


YesNo = Literal["yes", "no", "not_assessed"]


class SessionNoteIn(BaseModel):
    """The session form. Every risk question must be answered explicitly ('not assessed' is a valid answer; a blank is not)."""

    mode: Literal["chat", "video", "both"] = "chat"
    concerns: str = Field(min_length=3, max_length=3000)
    observations: str | None = Field(default=None, max_length=3000)
    ideation: YesNo
    plan: YesNo
    intent: YesNo
    means_access: YesNo
    previous_attempt: YesNo
    protective_factors: str = Field(min_length=3, max_length=2000)
    risk_level: Literal["low", "medium", "high"]
    safety_plan: Literal["not_needed", "created", "updated", "reviewed"]
    safety_plan_copy_given: bool = False
    impression: str | None = Field(default=None, max_length=2000)
    actions_taken: str = Field(min_length=3, max_length=3000)
    follow_up: str = Field(min_length=3, max_length=3000)
    follow_up_date: date | None = None
    referral: str | None = Field(default=None, max_length=1000)
    emergency_services_contacted: bool = False

    @field_validator("concerns", "actions_taken", "follow_up", "protective_factors")
    @classmethod
    def _text(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("This field is required.")
        return v

    @field_validator("follow_up_date")
    @classmethod
    def _not_past(cls, v: date | None) -> date | None:
        if v is not None and v < date.today():
            raise ValueError("The follow-up date cannot be in the past.")
        return v


class SessionNoteOut(SessionNoteIn):
    case_id: int
    doctor_name: str
    created_at: datetime


class SignalIn(BaseModel):
    kind: Literal["request", "accept", "decline", "end", "offer", "answer", "ice"]
    payload: dict | None = None

    @field_validator("payload")
    @classmethod
    def _small(cls, v: dict | None) -> dict | None:
        import json as _json

        if v is not None and len(_json.dumps(v)) > 20000:
            raise ValueError("That message is too large.")
        return v


class SignalOut(BaseModel):
    id: int
    sender_role: str
    kind: str
    payload: dict | None = None


class IceOut(BaseModel):
    ice_servers: list[dict]


class CaseDetailOut(BaseModel):
    """Who the doctor is speaking with, for an accepted case: the details the Indian telemedicine rules expect a doctor to hold, and whether the
    person is a minor (a consultation with a minor needs an identified adult family member)."""

    case_id: int
    state: str
    full_name: str
    age: int
    is_minor: bool
    guardian_name: str | None = None
    guardian_consent_status: str | None = None
    phone: str | None = None
    emergency_contact: str | None = None
    video_used: bool = False


class MyCaseOut(BaseModel):
    case_id: int
    first_name: str
    state: str
    accepted_at: datetime | None = None


class MessageOut(BaseModel):
    id: int
    text: str
    created_at: datetime
    reply: SupportReplyOut
    care_status: str                          # waiting | being_read | reviewed: what is really true about whether a person has opened it
    status_text: str                          # the reviewed sentence for that state


class ReviewerMessageSummary(BaseModel):
    """Triage the queue without opening anything: no message text."""

    id: int
    user_name: str
    created_at: datetime
    priority: Literal["low", "medium", "high"]
    status: str
    rule_flagged: bool
    reviewer_raised: bool
    baseline_floor: str
    opened: bool = False
    urgent: bool = False                      # the MESSAGE itself is urgent (not just a High floor from the check-in)


class UrgentAlertsOut(BaseModel):
    """Counts only, so it is safe to poll often: no names, no text."""

    urgent_waiting: int
    urgent_unopened: int
    oldest_unopened_seconds: int | None
    latest_urgent_id: int | None


class ReviewEventOut(BaseModel):
    id: int
    kind: str
    from_urgency: str | None
    to_urgency: str
    notes: str
    reviewer_name: str
    created_at: datetime


class ReviewerMessageOut(BaseModel):
    id: int
    user_id: str
    user_name: str
    user_email: str
    text: str
    created_at: datetime
    priority: Literal["low", "medium", "high"]
    initial_priority: str
    status: str
    rule_level: str
    rule_hits: list[str]
    baseline_floor: str
    baseline_known: bool
    baseline_risk: str | None
    checkin_id: int | None
    reasons: list[str]
    reviewer_note: str
    model_version: str
    policy_version: str
    reply_shown: SupportReplyOut
    history: list[ReviewEventOut]


class EscalateIn(BaseModel):
    to: Literal["medium", "high"]
    reason: str = Field(min_length=3, max_length=500)


class ReviewIn(BaseModel):
    urgency: Literal["low", "medium", "high"]
    notes: str = Field(default="", max_length=2000)
