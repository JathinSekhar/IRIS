from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, user_out
from ..models import CheckIn, User
from ..schemas import CheckinIn, CheckinOut
from ..services import questionnaire as qn
from ..services.scoring import score

router = APIRouter(prefix="/api/checkin", tags=["check-in"])


@router.get("/questionnaire", response_model=qn.Questionnaire)
def get_questionnaire(_: User = Depends(get_current_user)) -> qn.Questionnaire:
    return qn.QUESTIONNAIRE


@router.post("", response_model=CheckinOut, status_code=status.HTTP_201_CREATED)
def submit(body: CheckinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CheckinOut:
    if not user_out(db, user).consent_accepted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Consent is required before the check-in.")

    if body.skipped:
        row = CheckIn(user_id=user.id, skipped=True, questionnaire_version=qn.VERSION, baseline_risk="unknown")
    else:
        try:
            answers = qn.clean_answers(body.answers)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
        result = score(answers)
        free_text = answers.get("a1") if isinstance(answers.get("a1"), str) else None
        row = CheckIn(
            user_id=user.id,
            skipped=False,
            questionnaire_version=qn.VERSION,
            answers=answers,
            scores=dict(result),
            baseline_risk=result["baseline_risk"],
            safety_flag=result["safety"]["flag"],
            escalated=result["safety"]["escalate"],
            free_text=free_text,
        )
    db.add(row)
    db.commit()
    return CheckinOut(
        id=row.id,
        skipped=row.skipped,
        safety_flag=row.safety_flag,
        show_crisis_resources=row.safety_flag,
        created_at=row.created_at,
    )
