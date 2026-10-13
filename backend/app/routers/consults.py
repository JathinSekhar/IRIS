from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, user_out
from ..models import AuditLog, ConsultCase, User, utcnow
from ..schemas import ConsultOut, ConsultRequestIn, ThreadMessageIn, ThreadMessageOut
from ..services import consult, triage

router = APIRouter(prefix="/api/consults", tags=["consults"])


def _out(db: Session, c: ConsultCase) -> ConsultOut:
    helplines = [{"name": n, "detail": d, "number": num, "tel": tel} for n, d, num, tel in triage.support.HELPLINES]
    return ConsultOut(id=c.id, state=c.state, status_text=consult.status_text(db, c), created_at=c.created_at,
                      doctor_name=c.doctor.full_name if c.state == consult.ACCEPTED and c.doctor else None, helplines=helplines)


@router.get("/current", response_model=ConsultOut | None)
def current(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConsultOut | None:
    """The person's open or accepted request, if any. Nobody else's case is ever returned."""
    c = consult.live_case(db, user.id)
    return _out(db, c) if c else None


@router.get("/notice")
def notice(user: User = Depends(get_current_user)) -> dict:
    """What will be shared, said to the person before they agree."""
    return {"share_notice": consult.SHARE_NOTICE}


@router.post("", response_model=ConsultOut, status_code=status.HTTP_201_CREATED)
def request_doctor(body: ConsultRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConsultOut:
    """Ask to talk to a doctor. Needs the person's explicit agreement to share. One live request at a time: asking again returns the same one."""
    if user.role != "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a person using IRIS can ask for a doctor.")
    if not user_out(db, user).consent_accepted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Consent is required before you can ask for a doctor.")
    if not body.share:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A doctor can only help if you agree to share your recent messages and check-in answers.")
    existing = consult.live_case(db, user.id)
    if existing:
        return _out(db, existing)
    case = ConsultCase(user_id=user.id, source="user", share_consent=True)
    db.add(case)
    db.add(AuditLog(actor_id=user.id, action="request_doctor", target_type="consult", target_id="new"))
    db.commit()
    db.refresh(case)
    return _out(db, case)


@router.post("/{case_id}/cancel", response_model=ConsultOut)
def cancel(case_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConsultOut:
    case = db.get(ConsultCase, case_id)
    if case is None or case.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if case.state == consult.OPEN:
        case.state = consult.CANCELLED
        case.closed_at = utcnow()
        db.commit()
    return _out(db, case)


def _owned_accepted(db: Session, case_id: int, user: User) -> ConsultCase:
    case = db.get(ConsultCase, case_id)
    if case is None or case.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if case.state == consult.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This conversation has ended. You can ask for a doctor again at any time.")
    if case.state != consult.ACCEPTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can talk here once a doctor has accepted.")
    return case


def _thread_out(rows, viewer_id, show_flag: bool) -> list[ThreadMessageOut]:
    return [ThreadMessageOut(id=m.id, sender_role=m.sender_role, mine=m.sender_id == viewer_id, text=m.text, created_at=m.created_at,
                             urgent=bool(m.urgent and show_flag)) for m in rows]


@router.get("/{case_id}/messages", response_model=list[ThreadMessageOut])
def thread_messages(case_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ThreadMessageOut]:
    case = db.get(ConsultCase, case_id)
    if case is None or case.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return _thread_out(consult.thread(db, case.id), user.id, show_flag=False)


@router.post("/{case_id}/messages", response_model=ThreadMessageOut, status_code=status.HTTP_201_CREATED)
def send_thread_message(case_id: int, body: ThreadMessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ThreadMessageOut:
    case = _owned_accepted(db, case_id, user)
    if consult.too_fast(db, case.id, user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You are sending messages very quickly. Please wait a moment.")
    m = consult.add_message(db, case, user, "user", body.text)
    return _thread_out([m], user.id, show_flag=False)[0]
