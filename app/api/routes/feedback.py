from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.pilot_feedback import (
    feedback_payload,
    feedback_summary_payload,
    list_feedback,
)


router = APIRouter()


@router.get("")
def get_feedback(session: Session = Depends(get_session)) -> dict:
    return {"feedback": [feedback_payload(item) for item in list_feedback(session)]}


@router.get("/summary")
def get_feedback_summary(session: Session = Depends(get_session)) -> dict:
    return feedback_summary_payload(list_feedback(session, limit=1000))
