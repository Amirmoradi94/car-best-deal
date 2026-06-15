from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.decision_reports import decision_report_payload, get_decision_report


router = APIRouter()


@router.get("/{report_id}")
def get_report(report_id: str, session: Session = Depends(get_session)) -> dict:
    report = get_decision_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Decision report not found")
    return decision_report_payload(report)
