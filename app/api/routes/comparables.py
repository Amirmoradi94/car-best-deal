from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services.ai_extraction import AIExtractionService
from app.services.comparable_editing import (
    ComparableEditingError,
    update_comparable,
)
from app.services.decision_reports import create_decision_report, decision_report_payload
from app.storage.object_store import LocalObjectStore


router = APIRouter()


class ComparableUpdateRequest(BaseModel):
    included: bool
    excluded_reason: str | None = Field(default=None, max_length=1000)


@router.patch("/{comparable_id}")
def patch_comparable(
    comparable_id: str,
    payload: ComparableUpdateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        result = update_comparable(
            session,
            comparable_id=comparable_id,
            included=payload.included,
            excluded_reason=payload.excluded_reason,
        )
    except ComparableEditingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Comparable not found")

    report = create_decision_report(
        session,
        opportunity_id=result["opportunity_id"],
        object_store=LocalObjectStore(settings.object_store_root),
        ai_extractor=AIExtractionService(settings, session=session, object_store=LocalObjectStore(settings.object_store_root))
        if settings.ai_extraction_enabled
        else None,
    )
    return {
        **result,
        "report": decision_report_payload(report) if report is not None else None,
    }
