from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_doctor
from ..models import AuditLog, DoctorProfile, User
from ..schemas import DoctorAvailabilityIn, DoctorMeOut

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
