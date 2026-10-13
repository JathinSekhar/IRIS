from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_doctor
from ..models import AuditLog, ConsultCase, ConsultDecline, DoctorProfile, User
from ..schemas import DoctorAvailabilityIn, DoctorMeOut, MyCaseOut, OfferOut
from ..services import consult

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
        select(ConsultCase).where(ConsultCase.accepted_by == doctor.id, ConsultCase.state == consult.ACCEPTED).order_by(ConsultCase.accepted_at.desc())
    ).all()
    return [MyCaseOut(case_id=c.id, first_name=consult.person_first_name(c.user), state=c.state, accepted_at=c.accepted_at) for c in rows]
