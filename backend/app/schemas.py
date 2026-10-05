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
    id: int
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


class ReviewerCheckinOut(BaseModel):
    id: int
    user_id: int
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
