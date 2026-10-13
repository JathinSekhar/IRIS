from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_doctor
from ..models import AuditLog, ConsultCase, ConsultDecline, DoctorProfile, SessionNote, User
from ..deps import age_on
from ..schemas import (
    CaseDetailOut, CaseSummaryOut, DoctorAvailabilityIn, DoctorMeOut, MyCaseOut, OfferOut, SessionNoteIn, SessionNoteOut, SignalIn, SignalOut, ThreadMessageIn,
    ThreadMessageOut,
)
from ..services import case_summary, consult

router = APIRouter(prefix="/api/doctor", tags=["doctor"])


def _profile(db: Session, doctor: User) -> DoctorProfile:
    p = db.get(DoctorProfile, doctor.id)
    if p is None:                                     # a doctor account without a profile cannot be offered cases
        raise HTTPException(status.HTTP_409_CONFLICT, "This doctor account has no profile yet.")
    return p


def _out(doctor: User, p: DoctorProfile) -> DoctorMeOut:
    return DoctorMeOut(full_name=doctor.full_name, specialty=p.specialty, registration_number=p.registration_number,
                       languages=list(p.languages or []), on_duty=p.on_duty, on_duty_changed_at=p.on_duty_changed_at)


@router.get("/me", response_model=DoctorMeOut)
def me(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> DoctorMeOut:
    return _out(doctor, _profile(db, doctor))


@router.post("/availability", response_model=DoctorMeOut)
def set_availability(body: DoctorAvailabilityIn, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> DoctorMeOut:
    """Go on or off duty. Only on-duty doctors are offered cases. Every change is written to the audit log."""
    p = _profile(db, doctor)
    if p.on_duty != body.on_duty:
        p.on_duty = body.on_duty
        p.on_duty_changed_at = datetime.now(timezone.utc)
        db.add(AuditLog(actor_id=doctor.id, action="duty_on" if body.on_duty else "duty_off", target_type="doctor", target_id=str(doctor.id)))
        db.commit()
    return _out(doctor, p)


def _offer(db: Session, case: ConsultCase) -> OfferOut:
    s = consult.summary_for_doctor(db, case)
    return OfferOut(case_id=case.id, first_name=consult.person_first_name(case.user), created_at=case.created_at, source=case.source, **s)


@router.get("/offers", response_model=list[OfferOut])
def offers(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> list[OfferOut]:
    """Open requests this doctor has not passed on. Empty when off duty. Opening this list is written to the audit log, because it shows messages."""
    if not _profile(db, doctor).on_duty:
        return []
    declined = select(ConsultDecline.case_id).where(ConsultDecline.doctor_id == doctor.id)
    rows = db.scalars(
        select(ConsultCase).where(ConsultCase.state == consult.OPEN, ConsultCase.share_consent.is_(True), ConsultCase.id.not_in(declined))
        .order_by(ConsultCase.created_at)
    ).all()
    out = [_offer(db, c) for c in rows]
    if out:
        db.add(AuditLog(actor_id=doctor.id, action="view_offers", target_type="consult", target_id=f"{len(out)} cases"))
        db.commit()
    out.sort(key=lambda o: (not o.urgent, {"high": 0, "medium": 1, "low": 2}.get(o.priority or "", 3), o.created_at))
    return out


@router.post("/offers/{case_id}/accept", response_model=MyCaseOut)
def accept(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> MyCaseOut:
    """First doctor to accept owns the case. A second doctor, or a cancelled request, gets a 409. Only on-duty doctors can accept."""
    if not _profile(db, doctor).on_duty:
        raise HTTPException(status.HTTP_409_CONFLICT, "Go on duty to accept cases.")
    case = db.get(ConsultCase, case_id)
    if case is None or not case.share_consent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    if not consult.claim(db, case_id, doctor.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "This request is no longer open.")
    db.add(AuditLog(actor_id=doctor.id, action="accept_case", target_type="consult", target_id=str(case_id)))
    db.commit()
    db.refresh(case)
    return MyCaseOut(case_id=case.id, first_name=consult.person_first_name(case.user), state=case.state, accepted_at=case.accepted_at)


@router.post("/offers/{case_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> None:
    case = db.get(ConsultCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    if db.get(ConsultDecline, (case_id, doctor.id)) is None:
        db.add(ConsultDecline(case_id=case_id, doctor_id=doctor.id))
        db.add(AuditLog(actor_id=doctor.id, action="decline_case", target_type="consult", target_id=str(case_id)))
        db.commit()


@router.get("/cases", response_model=list[MyCaseOut])
def my_cases(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> list[MyCaseOut]:
    rows = db.scalars(
        select(ConsultCase).where(ConsultCase.accepted_by == doctor.id, ConsultCase.state.in_((consult.ACCEPTED, consult.IN_SESSION, consult.CLOSED)))
        .order_by(ConsultCase.accepted_at.desc()).limit(40)
    ).all()
    return [MyCaseOut(case_id=c.id, first_name=consult.person_first_name(c.user), state=c.state, accepted_at=c.accepted_at) for c in rows]


def _my_accepted(db: Session, case_id: int, doctor: User) -> ConsultCase:
    case = db.get(ConsultCase, case_id)
    if case is None or case.accepted_by != doctor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


def _thread_out(rows, viewer_id) -> list[ThreadMessageOut]:
    return [ThreadMessageOut(id=m.id, sender_role=m.sender_role, mine=m.sender_id == viewer_id, text=m.text, created_at=m.created_at, urgent=m.urgent)
            for m in rows]


@router.get("/cases/{case_id}/messages", response_model=list[ThreadMessageOut])
def case_messages(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> list[ThreadMessageOut]:
    """The conversation with the person whose case this doctor accepted. Reading it is audited (at most once every five minutes per case)."""
    case = _my_accepted(db, case_id, doctor)
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    seen = db.scalar(select(AuditLog.id).where(AuditLog.actor_id == doctor.id, AuditLog.action == "view_thread", AuditLog.target_id == str(case_id),
                                               AuditLog.created_at > recent).limit(1))
    if seen is None:
        db.add(AuditLog(actor_id=doctor.id, action="view_thread", target_type="consult", target_id=str(case_id)))
        db.commit()
    return _thread_out(consult.thread(db, case.id), doctor.id)


@router.post("/cases/{case_id}/messages", response_model=ThreadMessageOut, status_code=status.HTTP_201_CREATED)
def send_case_message(case_id: int, body: ThreadMessageIn, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> ThreadMessageOut:
    case = _my_accepted(db, case_id, doctor)
    if case.state == consult.ACCEPTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start the conversation first.")
    if case.state != consult.IN_SESSION:
        raise HTTPException(status.HTTP_409_CONFLICT, "This conversation has ended.")
    if consult.too_fast(db, case.id, doctor.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You are sending messages very quickly. Please wait a moment.")
    m = consult.add_message(db, case, doctor, "doctor", body.text)
    return _thread_out([m], doctor.id)[0]


def _note_out(db: Session, n: SessionNote) -> SessionNoteOut:
    d = db.get(User, n.doctor_id)
    return SessionNoteOut(
        case_id=n.case_id, doctor_name=d.full_name if d else "", created_at=n.created_at, mode=n.mode, concerns=n.concerns, observations=n.observations,
        ideation=n.ideation, plan=n.plan, intent=n.intent, means_access=n.means_access, previous_attempt=n.previous_attempt,
        protective_factors=n.protective_factors, risk_level=n.risk_level, safety_plan=n.safety_plan, safety_plan_copy_given=n.safety_plan_copy_given,
        impression=n.impression, actions_taken=n.actions_taken, follow_up=n.follow_up, follow_up_date=n.follow_up_date, referral=n.referral,
        emergency_services_contacted=n.emergency_services_contacted,
    )


@router.post("/cases/{case_id}/close", response_model=SessionNoteOut)
def close_case(case_id: int, body: SessionNoteIn, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> SessionNoteOut:
    """End a conversation. The session form is required: no note, no close. The person is then told the conversation has ended and can ask again."""
    case = _my_accepted(db, case_id, doctor)
    if case.state not in consult.WITH_DOCTOR:
        raise HTTPException(status.HTTP_409_CONFLICT, "This conversation has already ended.")
    note = SessionNote(case_id=case.id, doctor_id=doctor.id, **body.model_dump())
    db.add(note)
    case.state = consult.CLOSED
    case.closed_at = datetime.now(timezone.utc)
    from sqlalchemy import delete

    from ..models import ConsultSignal

    db.execute(delete(ConsultSignal).where(ConsultSignal.case_id == case.id))      # set-up data holds network addresses: gone with the conversation
    db.add(AuditLog(actor_id=doctor.id, action="close_case", target_type="consult", target_id=str(case_id)))
    db.commit()
    db.refresh(note)
    return _note_out(db, note)


@router.get("/cases/{case_id}/note", response_model=SessionNoteOut)
def case_note(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> SessionNoteOut:
    _my_accepted(db, case_id, doctor)
    n = db.get(SessionNote, case_id)
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no session note yet.")
    return _note_out(db, n)


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
def case_detail(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> CaseDetailOut:
    """Who this doctor is speaking with: only for a case they accepted. Contact details are shown because the person asked for a doctor, and the read is audited."""
    case = _my_accepted(db, case_id, doctor)
    u = case.user
    age = age_on(u.date_of_birth)
    db.add(AuditLog(actor_id=doctor.id, action="view_case_detail", target_type="consult", target_id=str(case_id)))
    db.commit()
    return CaseDetailOut(case_id=case.id, state=case.state, full_name=u.full_name, age=age, is_minor=age < 18, guardian_name=u.guardian_name,
                         guardian_consent_status=u.guardian_consent_status, phone=u.phone, emergency_contact=u.emergency_contact,
                         video_used=case.video_used)


@router.post("/cases/{case_id}/call", response_model=SignalOut, status_code=status.HTTP_201_CREATED)
def call_signal(case_id: int, body: SignalIn, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> SignalOut:
    """Video call set-up from the doctor's side, on a case they own and while it is still open."""
    case = _my_accepted(db, case_id, doctor)
    if case.state == consult.ACCEPTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start the conversation first.")
    if case.state != consult.IN_SESSION:
        raise HTTPException(status.HTTP_409_CONFLICT, "This conversation has ended.")
    if consult.signals_too_fast(db, case.id, "doctor"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many call messages. Please wait a moment.")
    s = consult.add_signal(db, case, "doctor", body.kind, body.payload)
    if body.kind in ("request", "accept", "end"):
        db.add(AuditLog(actor_id=doctor.id, action=f"video_{body.kind}", target_type="consult", target_id=str(case.id)))
        db.commit()
    return SignalOut(id=s.id, sender_role=s.sender_role, kind=s.kind, payload=s.payload)


@router.get("/cases/{case_id}/call", response_model=list[SignalOut])
def call_poll(case_id: int, after: int = 0, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> list[SignalOut]:
    case = _my_accepted(db, case_id, doctor)
    return [SignalOut(id=s.id, sender_role=s.sender_role, kind=s.kind, payload=s.payload) for s in consult.signals_for(db, case.id, "doctor", after)]


@router.post("/cases/{case_id}/start", response_model=MyCaseOut)
def start_case(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> MyCaseOut:
    """The doctor begins the conversation. Until then the person is told the doctor has accepted and will begin when ready; chat and video are closed."""
    case = _my_accepted(db, case_id, doctor)
    if case.state == consult.ACCEPTED:
        case.state = consult.IN_SESSION
        case.started_at = datetime.now(timezone.utc)
        db.add(AuditLog(actor_id=doctor.id, action="start_case", target_type="consult", target_id=str(case_id)))
        db.commit()
    elif case.state != consult.IN_SESSION:
        raise HTTPException(status.HTTP_409_CONFLICT, "This conversation has ended.")
    return MyCaseOut(case_id=case.id, first_name=consult.person_first_name(case.user), state=case.state, accepted_at=case.accepted_at)


def _summary_out(db: Session, case: ConsultCase) -> CaseSummaryOut:
    from ..config import settings

    s = case_summary.build(db, case)
    return CaseSummaryOut(**s, ai_allowed=case.ai_summary_consent, ai_available=bool(settings.llm_enabled and settings.groq_api_key),
                          ai_summary=case.ai_summary, ai_summary_at=case.ai_summary_at, ai_disclosure=case_summary.AI_DISCLOSURE)


@router.get("/cases/{case_id}/summary", response_model=CaseSummaryOut)
def case_summary_view(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> CaseSummaryOut:
    """The rules-based summary (profile, check-in, chat). Nothing leaves the server for this. Audited."""
    case = _my_accepted(db, case_id, doctor)
    db.add(AuditLog(actor_id=doctor.id, action="view_summary", target_type="consult", target_id=str(case_id)))
    db.commit()
    return _summary_out(db, case)


@router.post("/cases/{case_id}/summary/ai", response_model=CaseSummaryOut)
def draft_ai_summary(case_id: int, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)) -> CaseSummaryOut:
    """Ask for an AI-written draft. Only if the person separately agreed; only on request; the minimum text is sent; every request is audited."""
    case = _my_accepted(db, case_id, doctor)
    if not case.ai_summary_consent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This person did not agree to an AI-drafted summary.")
    text = case_summary.draft_ai(db, case)
    db.add(AuditLog(actor_id=doctor.id, action="ai_summary_ok" if text else "ai_summary_failed", target_type="consult", target_id=str(case_id)))
    if text:
        case.ai_summary = text
        case.ai_summary_at = datetime.now(timezone.utc)
    db.commit()
    if not text:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The AI draft is not available right now. The summary above still works.")
    return _summary_out(db, case)
