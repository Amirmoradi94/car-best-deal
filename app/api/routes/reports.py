from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services.decision_reports import (
    REPORT_CSV_CONTENT_TYPE,
    REPORT_PDF_CONTENT_TYPE,
    decision_report_payload,
    ensure_decision_report_exports,
    get_decision_report,
)
from app.storage.object_store import LocalObjectStore


router = APIRouter()


@router.get("/{report_id}")
def get_report(report_id: str, session: Session = Depends(get_session)) -> dict:
    report = get_decision_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Decision report not found")
    return decision_report_payload(report)


@router.get("/{report_id}/pdf")
def download_report_pdf(
    report_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    report = _report_with_exports(report_id, session, settings)
    return _download_report_export(
        settings,
        object_key=report.pdf_object_key,
        content_type=REPORT_PDF_CONTENT_TYPE,
        filename=f"decision-report-v{report.version}.pdf",
    )


@router.get("/{report_id}/csv")
def download_report_csv(
    report_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    report = _report_with_exports(report_id, session, settings)
    return _download_report_export(
        settings,
        object_key=report.csv_object_key,
        content_type=REPORT_CSV_CONTENT_TYPE,
        filename=f"decision-report-v{report.version}.csv",
    )


def _report_with_exports(report_id: str, session: Session, settings: Settings):
    report = get_decision_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Decision report not found")
    return ensure_decision_report_exports(
        session,
        report,
        object_store=LocalObjectStore(settings.object_store_root),
    )


def _download_report_export(
    settings: Settings,
    *,
    object_key: str | None,
    content_type: str,
    filename: str,
) -> Response:
    if not object_key:
        raise HTTPException(status_code=404, detail="Report export not found")
    try:
        data = LocalObjectStore(settings.object_store_root).read_bytes(object_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report export object not found") from exc
    safe_filename = filename.replace("\\", "_").replace('"', "_")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )
