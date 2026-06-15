from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.domain.enums import OpportunityStage, SellerType
from app.scraping.contracts import SearchFilters
from app.services.ai_extraction import AIExtractionService
from app.services.decision_reports import (
    REPORT_CSV_CONTENT_TYPE,
    REPORT_PDF_CONTENT_TYPE,
    create_decision_report,
    decision_report_payload,
    ensure_decision_report_exports,
    get_latest_decision_report,
    mark_latest_decision_report_stale,
    render_decision_report_html,
)
from app.services.comparable_editing import (
    ComparableEditingError,
    list_opportunity_comparables,
    pricing_analysis_payload,
    recalculate_opportunity_pricing,
)
from app.services.candidate_analysis import (
    candidate_analysis_summary_payload,
    image_analysis_summary_payload,
    latest_candidate_analysis,
    latest_image_analysis,
)
from app.services.dealer_corrections import (
    DealerCorrectionError,
    create_dealer_correction,
    dealer_correction_payload,
    dealer_correction_summary_payload,
    list_dealer_corrections,
)
from app.services.opportunity_promotion import (
    get_opportunity_with_candidate,
    list_opportunities,
    opportunity_payload,
    promote_candidate_to_opportunity,
    update_opportunity_contact,
    update_opportunity_stage,
    update_opportunity_visit_checklist,
)
from app.services.opportunity_documents import (
    DocumentUploadError,
    document_payload,
    document_summary_payload,
    get_opportunity_document,
    list_opportunity_documents,
    store_opportunity_document,
)
from app.services.pilot_feedback import (
    create_opportunity_feedback,
    feedback_payload,
    list_opportunity_feedback,
)
from app.services.previsit_persistence import persist_search_run
from app.services.search_pipeline import SearchPipeline
from app.services.opportunity_title import (
    TitleEvidenceError,
    create_title_evidence,
    create_title_evidence_from_document,
    list_title_evidence,
    title_evidence_payload,
    title_evidence_summary_payload,
)
from app.services.lien_profiles import lien_profile_summary_payload, list_lien_profiles
from app.services.recall_compliance import (
    RecallComplianceError,
    create_recall_compliance_evidence,
    create_recall_compliance_from_document,
    list_recall_compliance_evidence,
    recall_compliance_payload,
    recall_compliance_summary_payload,
)
from app.services.vehicle_history import (
    history_payload,
    list_opportunity_history,
    upsert_opportunity_history,
)
from app.services.wholesale_evidence import (
    WholesaleEvidenceError,
    create_wholesale_evidence,
    create_wholesale_evidence_from_document,
    list_wholesale_evidence,
    wholesale_evidence_payload,
    wholesale_evidence_summary_payload,
)
from app.storage.object_store import LocalObjectStore


router = APIRouter()


class OpportunityStageUpdateRequest(BaseModel):
    stage: OpportunityStage
    override_missing_data_warning: bool = False


class OpportunityContactUpdateRequest(BaseModel):
    seller_contact_status: str | None = Field(default=None, max_length=80)
    seller_notes: str | None = Field(default=None, max_length=5000)


class OpportunityVisitChecklistUpdateRequest(BaseModel):
    vin_confirmed: bool | None = None
    service_records_requested: bool | None = None
    lien_status_checked: bool | None = None
    history_report_checked: bool | None = None
    extra_photos_requested: bool | None = None
    visit_appointment_set: bool | None = None


class DealerCorrectionRequest(BaseModel):
    entity_type: Literal["vehicle", "listing", "history", "title"]
    field_name: str = Field(max_length=80)
    new_value: Any
    reason: str | None = Field(default=None, max_length=1000)
    apply_to_future: bool = True


class OpportunityFromListingRequest(BaseModel):
    name: str = "Single listing intake"
    listing_url: str
    vin: str | None = None
    sources: Literal["both", "kijiji", "autotrader"] = "both"
    listing_limit: int = Field(default=25, ge=1, le=100)
    location_city: str = "Montreal"
    location_province: str = "QC"
    radius_km: int = Field(default=50, ge=1, le=1000)


class OpportunityFromVinRequest(BaseModel):
    name: str = "VIN intake"
    vin: str
    sources: Literal["both", "kijiji", "autotrader"] = "both"
    listing_limit: int = Field(default=25, ge=1, le=100)
    make: str | None = None
    model: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    location_city: str = "Montreal"
    location_province: str = "QC"
    radius_km: int = Field(default=50, ge=1, le=1000)


class AccidentClaimRequest(BaseModel):
    date: str | None = Field(default=None, max_length=40)
    amount_cad: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)
    severity: Literal["minor", "moderate", "major", "unknown"] = "unknown"


class RegistrationEventRequest(BaseModel):
    date: str | None = Field(default=None, max_length=40)
    province: str | None = Field(default=None, max_length=20)
    event: str | None = Field(default=None, max_length=200)


class OdometerRecordRequest(BaseModel):
    date: str | None = Field(default=None, max_length=40)
    mileage_km: int | None = Field(default=None, ge=0)
    source: str | None = Field(default=None, max_length=120)


class ServiceRecordRequest(BaseModel):
    date: str | None = Field(default=None, max_length=40)
    mileage_km: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)


class ImportHistoryRequest(BaseModel):
    date: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, max_length=80)
    event: str | None = Field(default=None, max_length=200)


class OpportunityHistoryRequest(BaseModel):
    source_type: Literal["manual", "carfax", "seller_document", "auction_report", "api"] = "manual"
    source_name: str | None = Field(default=None, max_length=120)
    report_identifier: str | None = Field(default=None, max_length=120)
    title_brand: Literal["clean", "rebuilt", "salvage", "flood", "fire", "irreparable", "unknown"] = "unknown"
    accident_claims: list[AccidentClaimRequest] = Field(default_factory=list, max_length=50)
    registration_events: list[RegistrationEventRequest] = Field(default_factory=list, max_length=100)
    owners_count: int | None = Field(default=None, ge=0)
    odometer_records: list[OdometerRecordRequest] = Field(default_factory=list, max_length=100)
    odometer_issue: bool | None = None
    service_records_count: int | None = Field(default=None, ge=0)
    service_records: list[ServiceRecordRequest] = Field(default_factory=list, max_length=100)
    import_history: list[ImportHistoryRequest] = Field(default_factory=list, max_length=50)
    salvage_status: Literal["clear", "reported", "unknown"] = "unknown"
    flood_status: Literal["clear", "reported", "unknown"] = "unknown"
    fire_status: Literal["clear", "reported", "unknown"] = "unknown"
    theft_status: Literal["clear", "reported", "unknown"] = "unknown"
    summary: str | None = Field(default=None, max_length=5000)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OpportunityFeedbackCreateRequest(BaseModel):
    usefulness_rating: int = Field(ge=1, le=5)
    accuracy_rating: int = Field(ge=1, le=5)
    dealer_decision: Literal["undecided", "pursue", "pass", "contacted", "visited", "offered", "bought"] = "undecided"
    missing_info: list[str] = Field(default_factory=list, max_length=20)
    incorrect_info: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=5000)


class OpportunityTitleEvidenceRequest(BaseModel):
    source_type: Literal[
        "manual",
        "uvip",
        "ppsa_lookup",
        "ppsr_lookup",
        "seller_ownership",
        "lender_payout",
        "lien_release",
        "document_upload",
    ] = "manual"
    title_clearance_status: Literal[
        "unknown",
        "needs_review",
        "clear",
        "lien_found",
        "payout_pending",
        "payout_ready",
        "payout_paid",
        "released",
        "blocked",
    ] = "unknown"
    provider: str | None = Field(default=None, max_length=120)
    lookup_reference: str | None = Field(default=None, max_length=120)
    checked_at: str | None = Field(default=None, max_length=40)
    document_id: str | None = None
    seller_name: str | None = Field(default=None, max_length=160)
    registered_owner_name: str | None = Field(default=None, max_length=160)
    ownership_verified: bool | None = None
    lienholder_name: str | None = Field(default=None, max_length=160)
    lien_amount_cad: float | None = Field(default=None, ge=0)
    payout_required: bool | None = None
    payout_amount_cad: float | None = Field(default=None, ge=0)
    payout_due_date: str | None = Field(default=None, max_length=40)
    payout_status: Literal["unknown", "not_required", "requested", "received", "paid", "released"] = "unknown"
    notes: str | None = Field(default=None, max_length=5000)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OpportunityRecallComplianceRequest(BaseModel):
    source_type: Literal[
        "manual",
        "transport_canada",
        "oem_portal",
        "dealer_service",
        "import_compliance",
        "riv",
        "document_upload",
    ] = "manual"
    recall_status: Literal[
        "unknown",
        "not_checked",
        "no_open_recalls",
        "open_recall",
        "incomplete",
        "completed",
        "needs_review",
    ] = "unknown"
    compliance_status: Literal[
        "unknown",
        "not_applicable",
        "needs_review",
        "compliant",
        "non_compliant",
        "needs_inspection",
        "import_pending",
        "blocked",
    ] = "unknown"
    provider: str | None = Field(default=None, max_length=120)
    lookup_reference: str | None = Field(default=None, max_length=120)
    checked_at: str | None = Field(default=None, max_length=40)
    document_id: str | None = None
    campaign_number: str | None = Field(default=None, max_length=120)
    campaign_description: str | None = Field(default=None, max_length=1000)
    remedy_status: Literal[
        "unknown",
        "not_required",
        "required",
        "scheduled",
        "completed",
        "parts_unavailable",
    ] = "unknown"
    completion_date: str | None = Field(default=None, max_length=40)
    import_country: str | None = Field(default=None, max_length=80)
    import_form: str | None = Field(default=None, max_length=120)
    riv_case_number: str | None = Field(default=None, max_length=120)
    inspection_required: bool | None = None
    inspection_deadline: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=5000)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OpportunityWholesaleEvidenceRequest(BaseModel):
    source_type: Literal[
        "manual",
        "canadian_black_book",
        "manheim_mmr",
        "openlane",
        "adesa",
        "traderev",
        "auction_report",
        "trade_in_appraisal",
        "document_upload",
    ] = "manual"
    provider: str | None = Field(default=None, max_length=120)
    lookup_reference: str | None = Field(default=None, max_length=120)
    checked_at: str | None = Field(default=None, max_length=40)
    document_id: str | None = None
    region: str | None = Field(default=None, max_length=80)
    wholesale_low_cad: float | None = Field(default=None, ge=0)
    wholesale_avg_cad: float | None = Field(default=None, ge=0)
    wholesale_high_cad: float | None = Field(default=None, ge=0)
    trade_in_value_cad: float | None = Field(default=None, ge=0)
    retail_value_cad: float | None = Field(default=None, ge=0)
    auction_sale_low_cad: float | None = Field(default=None, ge=0)
    auction_sale_avg_cad: float | None = Field(default=None, ge=0)
    auction_sale_high_cad: float | None = Field(default=None, ge=0)
    bid_count: int | None = Field(default=None, ge=0)
    bidder_count: int | None = Field(default=None, ge=0)
    high_bid_cad: float | None = Field(default=None, ge=0)
    sale_price_cad: float | None = Field(default=None, ge=0)
    reserve_price_cad: float | None = Field(default=None, ge=0)
    condition_grade: Literal[
        "unknown",
        "rough",
        "average",
        "clean",
        "extra_clean",
        "auction_1",
        "auction_2",
        "auction_3",
        "auction_4",
        "auction_5",
    ] = "unknown"
    condition_score: float | None = Field(default=None, ge=0, le=5)
    condition_notes: str | None = Field(default=None, max_length=2000)
    buyer_fee_cad: float | None = Field(default=None, ge=0)
    transport_estimate_cad: float | None = Field(default=None, ge=0)
    reconditioning_estimate_cad: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=5000)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def get_opportunities(session: Session = Depends(get_session)) -> dict:
    return {
        "opportunities": [
            _opportunity_response(session, opportunity, candidate)
            for opportunity, candidate in list_opportunities(session)
        ]
    }


@router.post("/from-listing")
async def create_opportunity_from_listing(
    payload: OpportunityFromListingRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    filters = SearchFilters(
        location_city=payload.location_city,
        location_province=payload.location_province,
        radius_km=payload.radius_km,
        seller_type=SellerType.UNKNOWN,
        limit=payload.listing_limit,
    )
    pipeline = SearchPipeline(
        settings,
        ai_extractor=AIExtractionService(settings, session=session) if settings.ai_extraction_enabled else None,
    )
    try:
        search_result = await pipeline.run_single_listing_analysis_with_statuses(
            payload.listing_url,
            filters,
            sources=_sources_from_request(payload.sources),
            vin=payload.vin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not search_result.scored_items:
        raise HTTPException(status_code=404, detail="Listing analysis produced no candidate")

    search_id = str(uuid4())
    run = persist_search_run(
        session,
        search_id=search_id,
        name=payload.name,
        filters=filters,
        scored_items=search_result.scored_items,
        source_statuses=search_result.source_status_payload(),
        intake_metadata={
            "mode": "single_listing",
            "listing_url": payload.listing_url,
            "vin": payload.vin,
            "direct_promote_available": True,
        },
    )
    candidate_id = _first_candidate_id(session, run.id)
    if candidate_id is None:
        raise HTTPException(status_code=404, detail="Listing analysis produced no candidate")

    result = promote_candidate_to_opportunity(session, run_id=run.id, candidate_id=candidate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate snapshot not found")
    opportunity, candidate = result
    return {
        "status": "promoted",
        "run_id": run.id,
        "candidate_id": candidate.id,
        "search_id": search_id,
        "intake_mode": "single_listing",
        "listing_url": payload.listing_url,
        "vin": payload.vin,
        "source_statuses": search_result.source_status_payload(),
        "opportunity": _opportunity_response(session, opportunity, candidate),
    }


@router.post("/from-vin")
async def create_opportunity_from_vin(
    payload: OpportunityFromVinRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    filters = SearchFilters(
        make=payload.make,
        model=payload.model,
        year_min=payload.year_min,
        year_max=payload.year_max,
        location_city=payload.location_city,
        location_province=payload.location_province,
        radius_km=payload.radius_km,
        seller_type=SellerType.UNKNOWN,
        limit=payload.listing_limit,
    )
    pipeline = SearchPipeline(
        settings,
        ai_extractor=AIExtractionService(settings, session=session) if settings.ai_extraction_enabled else None,
    )
    try:
        search_result = await pipeline.run_vin_analysis_with_statuses(
            payload.vin,
            filters,
            sources=_sources_from_request(payload.sources),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not search_result.scored_items:
        raise HTTPException(status_code=404, detail="VIN analysis produced no candidate")

    search_id = str(uuid4())
    run = persist_search_run(
        session,
        search_id=search_id,
        name=payload.name,
        filters=filters,
        scored_items=search_result.scored_items,
        source_statuses=search_result.source_status_payload(),
        intake_metadata={
            "mode": "vin",
            "listing_url": None,
            "vin": payload.vin,
            "direct_promote_available": True,
        },
    )
    candidate_id = _first_candidate_id(session, run.id)
    if candidate_id is None:
        raise HTTPException(status_code=404, detail="VIN analysis produced no candidate")

    result = promote_candidate_to_opportunity(session, run_id=run.id, candidate_id=candidate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate snapshot not found")
    opportunity, candidate = result
    return {
        "status": "promoted",
        "run_id": run.id,
        "candidate_id": candidate.id,
        "search_id": search_id,
        "intake_mode": "vin",
        "vin": payload.vin,
        "source_statuses": search_result.source_status_payload(),
        "opportunity": _opportunity_response(session, opportunity, candidate),
    }


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opportunity, candidate = result
    return _opportunity_response(session, opportunity, candidate)


@router.patch("/{opportunity_id}/stage")
def patch_opportunity_stage(
    opportunity_id: str,
    payload: OpportunityStageUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    result = update_opportunity_stage(
        session,
        opportunity_id=opportunity_id,
        stage=payload.stage,
        override_missing_data_warning=payload.override_missing_data_warning,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    opportunity, candidate, stage_update_warning = result
    latest_report = mark_latest_decision_report_stale(session, opportunity_id=opportunity.id)
    response = _opportunity_response(session, opportunity, candidate, latest_report=latest_report)
    if stage_update_warning is not None:
        response["stage_update_warning"] = stage_update_warning
    return response


@router.patch("/{opportunity_id}/contact")
def patch_opportunity_contact(
    opportunity_id: str,
    payload: OpportunityContactUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    result = update_opportunity_contact(
        session,
        opportunity_id=opportunity_id,
        seller_contact_status=payload.seller_contact_status,
        seller_notes=payload.seller_notes,
        update_seller_contact_status="seller_contact_status" in payload.model_fields_set,
        update_seller_notes="seller_notes" in payload.model_fields_set,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    opportunity, candidate = result
    latest_report = mark_latest_decision_report_stale(session, opportunity_id=opportunity.id)
    return _opportunity_response(session, opportunity, candidate, latest_report=latest_report)


@router.patch("/{opportunity_id}/visit-checklist")
def patch_opportunity_visit_checklist(
    opportunity_id: str,
    payload: OpportunityVisitChecklistUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    result = update_opportunity_visit_checklist(
        session,
        opportunity_id=opportunity_id,
        checklist_patch=payload.model_dump(exclude_none=True),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    opportunity, candidate = result
    latest_report = mark_latest_decision_report_stale(session, opportunity_id=opportunity.id)
    return _opportunity_response(session, opportunity, candidate, latest_report=latest_report)


@router.put("/{opportunity_id}/history")
async def put_opportunity_history(
    opportunity_id: str,
    payload: OpportunityHistoryRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    history_data = payload.model_dump(mode="json")
    extraction_result = None
    history_text = _history_extraction_text(history_data)
    if history_text and settings.ai_extraction_enabled:
        extraction_result = await AIExtractionService(
            settings,
            session=session,
            object_store=LocalObjectStore(settings.object_store_root),
        ).vehicle_history(opportunity_id=opportunity_id, text=history_text)
        if extraction_result is not None:
            history_data = _merge_history_ai_extraction(history_data, extraction_result.parsed_output)
            raw_payload = dict(history_data.get("raw_payload") or {})
            raw_payload["ai_extraction"] = extraction_result.reference()
            raw_payload["ai_extracted_fields"] = extraction_result.parsed_output
            history_data["raw_payload"] = raw_payload

    result = upsert_opportunity_history(
        session,
        opportunity_id=opportunity_id,
        history_data=history_data,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    profile, opportunity, candidate = result
    latest_report = mark_latest_decision_report_stale(session, opportunity_id=opportunity.id)
    return {
        "history": history_payload(profile),
        "opportunity": _opportunity_response(session, opportunity, candidate, latest_report=latest_report),
        "ai_extraction": extraction_result.reference() if extraction_result is not None else None,
    }


@router.get("/{opportunity_id}/history")
def get_opportunity_history(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    history_items = list_opportunity_history(session, opportunity_id=opportunity_id)
    if history_items is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return {
        "latest": history_payload(history_items[0]) if history_items else None,
        "history": [history_payload(item) for item in history_items],
    }


@router.post("/{opportunity_id}/documents")
async def post_opportunity_document(
    opportunity_id: str,
    document_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    notes: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    data = await file.read()
    try:
        result = store_opportunity_document(
            session,
            opportunity_id=opportunity_id,
            document_type=document_type,
            filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            notes=notes,
            object_store=LocalObjectStore(settings.object_store_root),
            max_bytes=settings.document_upload_max_bytes,
        )
    except DocumentUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    title_result = create_title_evidence_from_document(
        session,
        opportunity_id=result.opportunity.id,
        document=result.document,
    )
    recall_result = create_recall_compliance_from_document(
        session,
        opportunity_id=result.opportunity.id,
        document=result.document,
    )
    wholesale_result = create_wholesale_evidence_from_document(
        session,
        opportunity_id=result.opportunity.id,
        document=result.document,
    )
    opportunity = (
        wholesale_result.opportunity
        if wholesale_result is not None
        else recall_result.opportunity
        if recall_result is not None
        else title_result.opportunity
        if title_result is not None
        else result.opportunity
    )
    latest_report = mark_latest_decision_report_stale(session, opportunity_id=opportunity.id)
    _, candidate = get_opportunity_with_candidate(session, opportunity.id) or (opportunity, None)
    return {
        "document": document_payload(result.document),
        "opportunity": _opportunity_response(
            session,
            opportunity,
            candidate,
            latest_report=latest_report,
        ),
        "title_evidence": title_evidence_payload(title_result.evidence) if title_result is not None else None,
        "recall_compliance": (
            recall_compliance_payload(recall_result.evidence) if recall_result is not None else None
        ),
        "wholesale_evidence": (
            wholesale_evidence_payload(wholesale_result.evidence) if wholesale_result is not None else None
        ),
    }


@router.get("/{opportunity_id}/documents")
def get_opportunity_documents(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    documents = list_opportunity_documents(session, opportunity_id=opportunity_id)
    if documents is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return document_summary_payload(documents)


@router.get("/{opportunity_id}/documents/{document_id}/download")
def download_opportunity_document(
    opportunity_id: str,
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    document = get_opportunity_document(
        session,
        opportunity_id=opportunity_id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        data = LocalObjectStore(settings.object_store_root).read_bytes(document.object_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document object not found") from exc
    filename = document.original_filename.replace("\\", "_").replace('"', "_")
    return Response(
        content=data,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{opportunity_id}/title-evidence")
def post_opportunity_title_evidence(
    opportunity_id: str,
    payload: OpportunityTitleEvidenceRequest,
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = create_title_evidence(
            session,
            opportunity_id=opportunity_id,
            evidence_data=payload.model_dump(mode="json"),
        )
    except TitleEvidenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    latest_report = mark_latest_decision_report_stale(session, opportunity_id=result.opportunity.id)
    _, candidate = get_opportunity_with_candidate(session, result.opportunity.id) or (result.opportunity, None)
    return {
        "title_evidence": title_evidence_payload(result.evidence),
        "opportunity": _opportunity_response(
            session,
            result.opportunity,
            candidate,
            latest_report=latest_report,
        ),
    }


@router.get("/{opportunity_id}/title-evidence")
def get_opportunity_title_evidence(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    evidence_items = list_title_evidence(session, opportunity_id=opportunity_id)
    if evidence_items is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return title_evidence_summary_payload(session, evidence_items)


@router.post("/{opportunity_id}/recall-compliance")
def post_opportunity_recall_compliance(
    opportunity_id: str,
    payload: OpportunityRecallComplianceRequest,
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = create_recall_compliance_evidence(
            session,
            opportunity_id=opportunity_id,
            evidence_data=payload.model_dump(mode="json"),
        )
    except RecallComplianceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    latest_report = mark_latest_decision_report_stale(session, opportunity_id=result.opportunity.id)
    _, candidate = get_opportunity_with_candidate(session, result.opportunity.id) or (result.opportunity, None)
    return {
        "recall_compliance": recall_compliance_payload(result.evidence),
        "opportunity": _opportunity_response(
            session,
            result.opportunity,
            candidate,
            latest_report=latest_report,
        ),
    }


@router.get("/{opportunity_id}/recall-compliance")
def get_opportunity_recall_compliance(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    evidence_items = list_recall_compliance_evidence(session, opportunity_id=opportunity_id)
    if evidence_items is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return recall_compliance_summary_payload(session, evidence_items)


@router.post("/{opportunity_id}/wholesale-evidence")
def post_opportunity_wholesale_evidence(
    opportunity_id: str,
    payload: OpportunityWholesaleEvidenceRequest,
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = create_wholesale_evidence(
            session,
            opportunity_id=opportunity_id,
            evidence_data=payload.model_dump(mode="json"),
        )
    except WholesaleEvidenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    latest_report = mark_latest_decision_report_stale(session, opportunity_id=result.opportunity.id)
    _, candidate = get_opportunity_with_candidate(session, result.opportunity.id) or (result.opportunity, None)
    return {
        "wholesale_evidence": wholesale_evidence_payload(result.evidence),
        "opportunity": _opportunity_response(
            session,
            result.opportunity,
            candidate,
            latest_report=latest_report,
        ),
    }


@router.get("/{opportunity_id}/wholesale-evidence")
def get_opportunity_wholesale_evidence(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opportunity, candidate = result
    evidence_items = list_wholesale_evidence(session, opportunity_id=opportunity.id) or []
    retail_max_buy = (candidate.pricing_summary or {}).get("max_buy_price_cad") if candidate is not None else None
    return wholesale_evidence_summary_payload(session, evidence_items, retail_max_buy_cad=retail_max_buy)


@router.get("/{opportunity_id}/comparables")
def get_opportunity_comparables(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    result = list_opportunity_comparables(session, opportunity_id=opportunity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return result


@router.post("/{opportunity_id}/recalculate")
def post_opportunity_recalculate(
    opportunity_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    if get_opportunity_with_candidate(session, opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    try:
        pricing = recalculate_opportunity_pricing(session, opportunity_id=opportunity_id)
    except ComparableEditingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report = create_decision_report(
        session,
        opportunity_id=opportunity_id,
        object_store=LocalObjectStore(settings.object_store_root),
        ai_extractor=AIExtractionService(settings, session=session, object_store=LocalObjectStore(settings.object_store_root))
        if settings.ai_extraction_enabled
        else None,
    )
    refreshed = get_opportunity_with_candidate(session, opportunity_id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opportunity, candidate = refreshed
    comparables = list_opportunity_comparables(session, opportunity_id=opportunity_id)
    return {
        "pricing_analysis": pricing_analysis_payload(pricing),
        "comparables": comparables,
        "report": decision_report_payload(report) if report is not None else None,
        "opportunity": _opportunity_response(
            session,
            opportunity,
            candidate,
            latest_report=report,
        ),
    }


@router.post("/{opportunity_id}/corrections")
def post_opportunity_correction(
    opportunity_id: str,
    payload: DealerCorrectionRequest,
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = create_dealer_correction(
            session,
            opportunity_id=opportunity_id,
            entity_type=payload.entity_type,
            field_name=payload.field_name,
            new_value=payload.new_value,
            reason=payload.reason,
            apply_to_future=payload.apply_to_future,
        )
    except DealerCorrectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    latest_report = mark_latest_decision_report_stale(session, opportunity_id=result.opportunity.id)
    return {
        "correction": dealer_correction_payload(result.correction),
        "opportunity": _opportunity_response(
            session,
            result.opportunity,
            result.candidate,
            latest_report=latest_report,
        ),
    }


@router.get("/{opportunity_id}/corrections")
def get_opportunity_corrections(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    corrections = list_dealer_corrections(session, opportunity_id=opportunity_id)
    if corrections is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return dealer_correction_summary_payload(corrections)


@router.post("/{opportunity_id}/feedback")
def post_opportunity_feedback(
    opportunity_id: str,
    payload: OpportunityFeedbackCreateRequest,
    session: Session = Depends(get_session),
) -> dict:
    feedback = create_opportunity_feedback(
        session,
        opportunity_id=opportunity_id,
        usefulness_rating=payload.usefulness_rating,
        accuracy_rating=payload.accuracy_rating,
        dealer_decision=payload.dealer_decision,
        missing_info=payload.missing_info,
        incorrect_info=payload.incorrect_info,
        notes=payload.notes,
    )
    if feedback is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return feedback_payload(feedback)


@router.get("/{opportunity_id}/feedback")
def get_opportunity_feedback(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    feedback_items = list_opportunity_feedback(session, opportunity_id=opportunity_id)
    if feedback_items is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return {"feedback": [feedback_payload(item) for item in feedback_items]}


@router.post("/{opportunity_id}/reports")
def post_opportunity_report(
    opportunity_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    report = create_decision_report(
        session,
        opportunity_id=opportunity_id,
        object_store=LocalObjectStore(settings.object_store_root),
        ai_extractor=AIExtractionService(settings, session=session, object_store=LocalObjectStore(settings.object_store_root))
        if settings.ai_extraction_enabled
        else None,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return decision_report_payload(report)


@router.get("/{opportunity_id}/reports/latest")
def get_latest_opportunity_report(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    if get_opportunity_with_candidate(session, opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    report = get_latest_decision_report(session, opportunity_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Decision report not found")
    return decision_report_payload(report)


@router.get("/{opportunity_id}/reports/latest/html", response_class=HTMLResponse)
def get_latest_opportunity_report_html(
    opportunity_id: str,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    if get_opportunity_with_candidate(session, opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    report = get_latest_decision_report(session, opportunity_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Decision report not found")
    return HTMLResponse(render_decision_report_html(report))


@router.get("/{opportunity_id}/reports/latest/pdf")
def download_latest_opportunity_report_pdf(
    opportunity_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    report = _latest_report_with_exports(opportunity_id, session, settings)
    return _download_report_export(
        settings,
        object_key=report.pdf_object_key,
        content_type=REPORT_PDF_CONTENT_TYPE,
        filename=f"decision-report-v{report.version}.pdf",
    )


@router.get("/{opportunity_id}/reports/latest/csv")
def download_latest_opportunity_report_csv(
    opportunity_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    report = _latest_report_with_exports(opportunity_id, session, settings)
    return _download_report_export(
        settings,
        object_key=report.csv_object_key,
        content_type=REPORT_CSV_CONTENT_TYPE,
        filename=f"decision-report-v{report.version}.csv",
    )


def _opportunity_response(
    session: Session,
    opportunity,
    candidate,
    *,
    latest_report=None,
) -> dict:
    response = opportunity_payload(opportunity, candidate)
    report = latest_report if latest_report is not None else get_latest_decision_report(session, opportunity.id)
    response["latest_report"] = _latest_report_summary(report)
    documents = list_opportunity_documents(session, opportunity_id=opportunity.id) or []
    response["documents"] = document_summary_payload(documents)
    title_items = list_title_evidence(session, opportunity_id=opportunity.id) or []
    response["title_evidence"] = title_evidence_summary_payload(session, title_items)
    lien_profiles = list_lien_profiles(session, opportunity.id)
    response["lien_profile"] = lien_profile_summary_payload(lien_profiles)
    response["candidate_analysis"] = candidate_analysis_summary_payload(
        latest_candidate_analysis(session, opportunity.id)
    )
    response["image_analysis"] = image_analysis_summary_payload(latest_image_analysis(session, opportunity.id))
    recall_items = list_recall_compliance_evidence(session, opportunity_id=opportunity.id) or []
    response["recall_compliance"] = recall_compliance_summary_payload(session, recall_items)
    wholesale_items = list_wholesale_evidence(session, opportunity_id=opportunity.id) or []
    retail_max_buy = (candidate.pricing_summary or {}).get("max_buy_price_cad") if candidate is not None else None
    response["wholesale_evidence"] = wholesale_evidence_summary_payload(
        session,
        wholesale_items,
        retail_max_buy_cad=retail_max_buy,
    )
    corrections = list_dealer_corrections(session, opportunity_id=opportunity.id) or []
    response["dealer_corrections"] = dealer_correction_summary_payload(corrections)
    response["comparables"] = list_opportunity_comparables(session, opportunity_id=opportunity.id) or {
        "count": 0,
        "included_count": 0,
        "excluded_count": 0,
        "comparables": [],
    }
    return response


def _latest_report_summary(report) -> dict | None:
    if report is None:
        return None
    return {
        "id": report.id,
        "version": report.version,
        "status": report.status,
        "recommendation": report.recommendation,
        "html_url": f"/api/opportunities/{report.opportunity_id}/reports/latest/html",
        "pdf_url": f"/api/opportunities/{report.opportunity_id}/reports/latest/pdf",
        "csv_url": f"/api/opportunities/{report.opportunity_id}/reports/latest/csv",
        "pdf_object_key": report.pdf_object_key,
        "csv_object_key": report.csv_object_key,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def _latest_report_with_exports(opportunity_id: str, session: Session, settings: Settings):
    if get_opportunity_with_candidate(session, opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    report = get_latest_decision_report(session, opportunity_id)
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


def _history_extraction_text(history_data: dict) -> str | None:
    raw_payload = history_data.get("raw_payload") or {}
    if not isinstance(raw_payload, dict):
        return None
    for key in ["document_text", "history_text", "ocr_text", "text"]:
        value = raw_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _merge_history_ai_extraction(history_data: dict, extracted: dict) -> dict:
    merged = dict(history_data)
    for key in [
        "source_type",
        "title_brand",
        "accident_claims",
        "odometer_issue",
        "summary",
    ]:
        value = extracted.get(key)
        if _empty_history_value(merged.get(key)) and value not in (None, [], ""):
            merged[key] = value
    return merged


def _empty_history_value(value) -> bool:
    return value in (None, "", [], {}, "unknown")


def _sources_from_request(sources: str) -> tuple[str, ...]:
    if sources == "both":
        return ("kijiji", "autotrader")
    return (sources,)


def _first_candidate_id(session: Session, run_id: str) -> str | None:
    from app.db.models import CandidateSnapshot
    from sqlalchemy import select

    candidate = session.scalar(
        select(CandidateSnapshot)
        .where(CandidateSnapshot.search_run_id == run_id)
        .order_by(CandidateSnapshot.rank.asc())
    )
    return candidate.id if candidate is not None else None
