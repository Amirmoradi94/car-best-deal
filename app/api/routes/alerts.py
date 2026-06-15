from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.alerts import alert_payload, list_alerts, mark_alert_read


router = APIRouter()


class AlertListResponse(BaseModel):
    alerts: list[dict] = Field(default_factory=list)


@router.get("", response_model=AlertListResponse)
def get_alerts(
    include_read: bool = True,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> AlertListResponse:
    return AlertListResponse(
        alerts=[
            alert_payload(alert)
            for alert in list_alerts(session, limit=max(1, min(limit, 100)), include_read=include_read)
        ]
    )


@router.patch("/{alert_id}/read")
def read_alert(alert_id: str, session: Session = Depends(get_session)) -> dict:
    alert = mark_alert_read(session, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert_payload(alert)
