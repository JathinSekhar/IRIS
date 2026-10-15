from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, user_out
from ..models import AuditLog, ConsultCase, DoctorOffer, DoctorProfile, User, utcnow
from ..config import settings
from ..schemas import ConsultOut, ConsultRequestIn, DoctorOfferOut, IceOut, SignalIn, SignalOut, ThreadMessageIn, ThreadMessageOut
from ..services import consult, triage

router = APIRouter(prefix="/api/consults", tags=["consults"])


def _out(db: Session, c: ConsultCase) -> ConsultOut:
    helplines = [{"name": n, "detail": d, "number": num, "tel": tel} for n, d, num, tel in triage.support.HELPLINES]
    prof = db.get(DoctorProfile, c.accepted_by) if c.state in consult.WITH_DOCTOR and c.accepted_by else None
    return ConsultOut(id=c.id, state=c.state, status_text=consult.status_text(db, c), created_at=c.created_at,
                      doctor_name=c.doctor.full_name if c.state in consult.WITH_DOCTOR and c.doctor else None,
                      doctor_specialty=prof.specialty if prof else None,
                      doctor_registration_number=prof.registration_number if prof else None, helplines=helplines,
                      waiting_long=consult.waiting_long(c))


@router.get("/current", response_model=ConsultOut | None)
def current(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConsultOut | None:
    """The person's open or accepted request, if any. Nobody else's case is ever returned."""
    c = consult.live_case(db, user.id)
    return _out(db, c) if c else None


@router.get("/offer", response_model=DoctorOfferOut | None)
def current_offer(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DoctorOfferOut | None:
    """The doctor offer waiting for this person's answer, if any. None while they already have a live request."""
    if consult.live_case(db, user.id) is not None:
        return None
    o = consult.open_offer(db, user.id)
    if o is None:
        return None
    title, body = consult.OFFER_TEXT[o.reason]
    return DoctorOfferOut(id=o.id, reason=o.reason, title=title, body=body)


@router.post("/offer/{offer_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_offer(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """'Not now'. Nothing is shared. A later urgent message can offer again."""
    o = db.get(DoctorOffer, offer_id)
    if o is None or o.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    if o.resolved_at is None:
        o.resolved_at, o.resolution = utcnow(), "dismissed"
        db.add(AuditLog(actor_id=user.id, action="dismiss_doctor_offer", target_type="user", target_id=str(user.id)))
        db.commit()


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
    offer = db.get(DoctorOffer, body.offer_id) if body.offer_id else None
    if offer is not None and (offer.user_id != user.id or offer.resolved_at is not None):
        offer = None
    reason = consult.urgent_reason_for(db, user.id)
    if offer is not None and offer.reason in consult.URGENT_REASONS:
        reason = offer.reason
    elif offer is not None and reason is None:
        reason = offer.reason                                             # a reviewer suggested it: shown to doctors, not marked urgent
    source = "user" if offer is None else ("reviewer" if offer.reason == "reviewer" else "system")
    case = ConsultCase(user_id=user.id, source=source, share_consent=True, ai_summary_consent=body.share_ai,
                       urgent=reason in consult.URGENT_REASONS, reason=reason)
    db.add(case)
    db.add(AuditLog(actor_id=user.id, action="request_doctor", target_type="consult", target_id="new"))
    db.commit()
    consult.resolve_offers(db, user.id, "accepted")
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
    if case.state == consult.ACCEPTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your doctor has accepted and will begin the conversation when they are ready.")
    if case.state != consult.IN_SESSION:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can talk here once a doctor has accepted.")
    return case


def _thread_out(rows, viewer_id, show_flag: bool) -> list[ThreadMessageOut]:
    return [ThreadMessageOut(id=m.id, sender_role=m.sender_role, mine=m.sender_id == viewer_id, text=m.text, created_at=m.created_at,
                             urgent=bool(m.urgent and show_flag), flag=m.flag if show_flag else None) for m in rows]


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


@router.get("/ice", response_model=IceOut)
def ice(user: User = Depends(get_current_user)) -> IceOut:
    """The STUN/TURN servers the browser uses to set up a call."""
    return IceOut(ice_servers=settings.ice_servers)


@router.post("/{case_id}/call", response_model=SignalOut, status_code=status.HTTP_201_CREATED)
def call_signal(case_id: int, body: SignalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SignalOut:
    """Video call set-up from the person's side. Only while a doctor has accepted. Nothing is sent to anyone but the doctor on this case."""
    case = _owned_accepted(db, case_id, user)
    if consult.signals_too_fast(db, case.id, "user"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many call messages. Please wait a moment.")
    s = consult.add_signal(db, case, "user", body.kind, body.payload)
    if body.kind in ("request", "accept", "end"):
        db.add(AuditLog(actor_id=user.id, action=f"video_{body.kind}", target_type="consult", target_id=str(case.id)))
        db.commit()
    return SignalOut(id=s.id, sender_role=s.sender_role, kind=s.kind, payload=s.payload)


@router.get("/{case_id}/call", response_model=list[SignalOut])
def call_poll(case_id: int, after: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SignalOut]:
    case = db.get(ConsultCase, case_id)
    if case is None or case.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return [SignalOut(id=s.id, sender_role=s.sender_role, kind=s.kind, payload=s.payload) for s in consult.signals_for(db, case.id, "user", after)]
