from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services.previsit_persistence import (
    get_candidate_snapshot,
    get_search_run_with_candidates,
    list_search_runs,
    update_candidate_workflow_state,
)
from app.services.candidate_analysis import (
    candidate_analysis_summary_payload,
    image_analysis_summary_payload,
    latest_candidate_analysis,
    latest_image_analysis,
)
from app.services.opportunity_promotion import opportunity_payload, promote_candidate_to_opportunity
from app.services.saved_searches import (
    create_saved_search,
    get_saved_search,
    list_saved_searches,
    saved_search_payload,
    saved_search_run_payload,
    update_saved_search_schedule,
)
from app.services.scheduled_search_refresh import validate_refresh_schedule
from app.services.search_execution import SearchRunInput, execute_search_run
from app.services.natural_language_search import interpret_natural_language_search


router = APIRouter()


class StructuredSearchFilters(BaseModel):
    make: str | None = None
    model: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    price_min_cad: int | None = None
    price_max_cad: int | None = None
    mileage_max_km: int | None = None
    location_city: str | None = None
    location_province: str | None = None
    radius_km: int | None = Field(default=None, ge=1, le=1000)
    seller_type: Literal["private", "dealer", "auction", "unknown"] | None = None


class SearchCreateRequest(BaseModel):
    name: str
    natural_language_query: str | None = None
    structured_filters: StructuredSearchFilters = Field(default_factory=StructuredSearchFilters)
    listing_limit: int = Field(default=25, ge=1, le=100)
    sources: Literal["both", "kijiji", "autotrader"] = "both"
    max_candidates: int = Field(default=50, ge=1, le=50)
    listing_url: str | None = None
    vin: str | None = None
    include_overpriced: bool = False
    scheduled: bool = False
    schedule_cron: str | None = Field(default=None, max_length=80)
    alerts_enabled: bool = False
    email_alerts_enabled: bool = False
    in_app_alerts_enabled: bool = True

    @field_validator("schedule_cron")
    @classmethod
    def validate_schedule_cron(cls, value: str | None) -> str | None:
        return validate_refresh_schedule(value)


class SearchRunRequest(BaseModel):
    name: str = "Ad hoc search"
    natural_language_query: str | None = None
    structured_filters: StructuredSearchFilters = Field(default_factory=StructuredSearchFilters)
    listing_limit: int = Field(default=25, ge=1, le=100)
    sources: Literal["both", "kijiji", "autotrader"] = "both"
    max_candidates: int = Field(default=50, ge=1, le=50)
    listing_url: str | None = None
    vin: str | None = None


class SearchScheduleUpdateRequest(BaseModel):
    scheduled: bool | None = None
    schedule_cron: str | None = Field(default=None, max_length=80)
    alerts_enabled: bool | None = None
    email_alerts_enabled: bool | None = None
    in_app_alerts_enabled: bool | None = None

    @field_validator("schedule_cron")
    @classmethod
    def validate_schedule_cron(cls, value: str | None) -> str | None:
        return validate_refresh_schedule(value)


class SearchRunResponse(BaseModel):
    run_id: str | None = None
    status: str
    search_id: str | None = None
    intake_mode: Literal["discovery", "single_listing", "vin"] = "discovery"
    listing_url: str | None = None
    vin: str | None = None
    direct_promote_available: bool = False
    normalized_filters: dict | None = None
    sources: list[str] = Field(default_factory=list)
    source_statuses: list[dict] = Field(default_factory=list)
    interpreted_filters: dict = Field(default_factory=dict)
    interpretation: dict = Field(default_factory=dict)
    ranked_opportunities: list[dict]


class CandidateWorkflowUpdateRequest(BaseModel):
    selected: bool | None = None
    hidden: bool | None = None
    seller_contact_status: str | None = Field(default=None, max_length=80)
    seller_notes: str | None = Field(default=None, max_length=5000)


class SearchInterpretRequest(BaseModel):
    natural_language_query: str | None = None
    structured_filters: StructuredSearchFilters = Field(default_factory=StructuredSearchFilters)


@router.post("")
def create_search(payload: SearchCreateRequest, session: Session = Depends(get_session)) -> dict:
    search = create_saved_search(
        session,
        name=payload.name,
        natural_language_query=payload.natural_language_query,
        structured_filters=payload.structured_filters.model_dump(exclude_none=True),
        listing_limit=payload.listing_limit,
        sources=payload.sources,
        max_candidates=payload.max_candidates,
        listing_url=payload.listing_url,
        vin=payload.vin,
        include_overpriced=payload.include_overpriced,
        scheduled=payload.scheduled,
        schedule_cron=payload.schedule_cron,
        alerts_enabled=payload.alerts_enabled,
        email_alerts_enabled=payload.email_alerts_enabled,
        in_app_alerts_enabled=payload.in_app_alerts_enabled,
    )
    return {"status": "created", **saved_search_payload(search)}


@router.get("")
def get_searches(session: Session = Depends(get_session)) -> dict:
    return {"searches": [saved_search_payload(search) for search in list_saved_searches(session)]}


@router.post("/interpret")
def interpret_search(payload: SearchInterpretRequest) -> dict:
    return interpret_natural_language_search(
        payload.natural_language_query,
        payload.structured_filters.model_dump(exclude_none=True),
    ).payload()


@router.post("/run", response_model=SearchRunResponse)
async def run_ad_hoc_search(
    payload: SearchRunRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SearchRunResponse:
    return await _run_search_request(
        search_id=str(uuid4()),
        payload=payload,
        session=session,
        settings=settings,
    )


@router.post("/{search_id}/run", response_model=SearchRunResponse)
async def run_search(
    search_id: str,
    payload: SearchRunRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SearchRunResponse:
    saved_search = get_saved_search(session, search_id)
    if payload is None:
        if saved_search is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
        payload = SearchRunRequest(**saved_search_run_payload(saved_search))

    return await _run_search_request(
        search_id=search_id,
        payload=payload,
        session=session,
        settings=settings,
        saved_search_id=saved_search.id if saved_search is not None else None,
    )


async def _run_search_request(
    *,
    search_id: str,
    payload: SearchRunRequest,
    session: Session,
    settings: Settings,
    saved_search_id: str | None = None,
) -> SearchRunResponse:
    execution = await execute_search_run(
        search_id=search_id,
        payload=SearchRunInput(
            name=payload.name,
            natural_language_query=payload.natural_language_query,
            structured_filters=payload.structured_filters.model_dump(exclude_none=True),
            listing_limit=payload.listing_limit,
            sources=payload.sources,
            max_candidates=payload.max_candidates,
            listing_url=payload.listing_url,
            vin=payload.vin,
        ),
        session=session,
        settings=settings,
        saved_search_id=saved_search_id,
    )
    return SearchRunResponse(
        run_id=execution.run_id,
        status="completed",
        search_id=execution.search_id,
        intake_mode=execution.intake_mode,
        listing_url=execution.listing_url,
        vin=execution.vin,
        direct_promote_available=execution.direct_promote_available,
        normalized_filters=execution.normalized_filters,
        sources=execution.sources,
        source_statuses=execution.source_statuses,
        interpreted_filters=execution.interpreted_filters,
        interpretation=execution.interpretation,
        ranked_opportunities=execution.ranked_opportunities,
    )


@router.get("/runs")
def get_runs(session: Session = Depends(get_session)) -> dict:
    return {"runs": [_run_payload(run) for run in list_search_runs(session)]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    result = get_search_run_with_candidates(session, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Search run not found")
    run, candidates = result
    return {
        **_run_payload(run),
        "ranked_opportunities": [_candidate_payload(candidate) for candidate in candidates],
    }


@router.get("/runs/{run_id}/candidates/{candidate_id}")
def get_run_candidate(run_id: str, candidate_id: str, session: Session = Depends(get_session)) -> dict:
    candidate = get_candidate_snapshot(session, run_id=run_id, candidate_id=candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate snapshot not found")
    return _candidate_payload(candidate)


@router.patch("/runs/{run_id}/candidates/{candidate_id}")
def update_run_candidate(
    run_id: str,
    candidate_id: str,
    payload: CandidateWorkflowUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    update_fields = payload.model_fields_set
    candidate = update_candidate_workflow_state(
        session,
        run_id=run_id,
        candidate_id=candidate_id,
        selected=payload.selected,
        hidden=payload.hidden,
        seller_contact_status=payload.seller_contact_status,
        seller_notes=payload.seller_notes,
        update_seller_contact_status="seller_contact_status" in update_fields,
        update_seller_notes="seller_notes" in update_fields,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate snapshot not found")
    return _candidate_payload(candidate)


@router.post("/runs/{run_id}/candidates/{candidate_id}/promote")
def promote_run_candidate(
    run_id: str,
    candidate_id: str,
    session: Session = Depends(get_session),
) -> dict:
    result = promote_candidate_to_opportunity(session, run_id=run_id, candidate_id=candidate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Candidate snapshot not found")
    opportunity, candidate = result
    response = opportunity_payload(opportunity, candidate)
    response["candidate_analysis"] = candidate_analysis_summary_payload(
        latest_candidate_analysis(session, opportunity.id)
    )
    response["image_analysis"] = image_analysis_summary_payload(latest_image_analysis(session, opportunity.id))
    return response


@router.patch("/{search_id}")
def update_search_schedule(
    search_id: str,
    payload: SearchScheduleUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    search = update_saved_search_schedule(
        session,
        search_id,
        scheduled=payload.scheduled,
        schedule_cron=payload.schedule_cron,
        alerts_enabled=payload.alerts_enabled,
        email_alerts_enabled=payload.email_alerts_enabled,
        in_app_alerts_enabled=payload.in_app_alerts_enabled,
    )
    if search is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return saved_search_payload(search)


@router.get("/{search_id}")
def get_search(search_id: str, session: Session = Depends(get_session)) -> dict:
    search = get_saved_search(session, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return saved_search_payload(search)


def _opportunity_payload(search_id: str, scored) -> dict:
    intake_mode = _candidate_intake_mode(scored.relevance_reasons)
    return {
        "search_id": search_id,
        "intake_mode": intake_mode,
        "direct_promote_available": intake_mode in {"single_listing", "vin"},
        "listing_id": scored.listing.id,
        "title": f"{scored.listing.vehicle.year} {scored.listing.vehicle.make} {scored.listing.vehicle.model} {scored.listing.vehicle.trim}",
        "source": scored.listing.source_name,
        "source_url": scored.listing.url,
        "year": scored.listing.vehicle.year,
        "make": scored.listing.vehicle.make,
        "model": scored.listing.vehicle.model,
        "trim": scored.listing.vehicle.trim,
        "vin": scored.listing.vehicle.vin,
        "mileage_km": scored.listing.vehicle.mileage_km,
        "body_style": scored.listing.vehicle.body_style,
        "drivetrain": scored.listing.vehicle.drivetrain,
        "asking_price_cad": scored.listing.asking_price_cad,
        "location_city": scored.listing.location_city,
        "location_province": scored.listing.location_province,
        "seller_type": scored.listing.seller_type,
        "deal_score": scored.deal_score,
        "recommendation": scored.recommendation,
        "estimated_retail_value_cad": scored.pricing.retail_mid_cad,
        "max_buy_price_cad": scored.pricing.max_buy_price_cad,
        "preliminary": scored.pricing.preliminary,
        "is_overpriced": scored.is_overpriced,
        "missing_data": scored.risk.missing_verifications,
        "relevance_score": scored.relevance_score,
        "relevance_reasons": scored.relevance_reasons,
        "image_count": len(scored.listing.image_urls),
        "image_risk_adjustment": scored.listing.image_risk_adjustment,
        "image_risk_reasons": scored.listing.image_risk_reasons,
    }


def _run_payload(run) -> dict:
    intake = _run_intake_metadata(run)
    return {
        "id": run.id,
        "search_id": run.search_id,
        "name": run.name,
        "status": run.status,
        "candidate_count": run.candidate_count,
        "listing_limit": run.listing_limit,
        "natural_language_query": run.natural_language_query,
        "structured_filters": run.structured_filters,
        "intake_mode": intake["mode"],
        "listing_url": intake["listing_url"],
        "vin": intake["vin"],
        "direct_promote_available": intake["direct_promote_available"],
        "source_statuses": run.source_statuses,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _candidate_payload(candidate) -> dict:
    pricing = candidate.pricing_summary
    risk = candidate.risk_summary
    intake_mode = _candidate_intake_mode(candidate.relevance_reasons)
    return {
        "id": candidate.id,
        "intake_mode": intake_mode,
        "direct_promote_available": intake_mode in {"single_listing", "vin"},
        "search_run_id": candidate.search_run_id,
        "rank": candidate.rank,
        "listing_id": candidate.listing_id,
        "title": candidate.title,
        "source": candidate.source_name,
        "source_url": candidate.source_url,
        "year": candidate.year,
        "make": candidate.make,
        "model": candidate.model,
        "trim": candidate.trim,
        "vin": candidate.vin,
        "mileage_km": candidate.mileage_km,
        "body_style": candidate.body_style,
        "drivetrain": candidate.drivetrain,
        "asking_price_cad": _json_number(candidate.asking_price_cad),
        "location_city": candidate.location_city,
        "location_province": candidate.location_province,
        "seller_type": candidate.seller_type,
        "deal_score": _json_number(candidate.deal_score),
        "recommendation": candidate.recommendation,
        "estimated_retail_value_cad": pricing.get("retail_mid_cad"),
        "max_buy_price_cad": pricing.get("max_buy_price_cad"),
        "preliminary": pricing.get("preliminary"),
        "is_overpriced": candidate.is_overpriced,
        "missing_data": risk.get("missing_verifications", []),
        "risk_summary": risk,
        "pricing_summary": pricing,
        "relevance_score": _json_number(candidate.relevance_score),
        "relevance_reasons": candidate.relevance_reasons,
        "image_count": len(candidate.image_urls),
        "image_urls": candidate.image_urls,
        "image_risk_adjustment": _json_number(candidate.image_risk_adjustment),
        "image_risk_reasons": candidate.image_risk_reasons,
        "ai_outputs": candidate.ai_outputs,
        "ai_risk_flags": risk.get("ai_risk_flags", []),
        "confidence_by_section": candidate.confidence_by_section,
        "selected": candidate.selected,
        "hidden": candidate.hidden,
        "seller_contact_status": candidate.seller_contact_status,
        "seller_notes": candidate.seller_notes,
        "opportunity_id": candidate.opportunity_id,
    }


def _run_intake_metadata(run) -> dict:
    intake = (run.structured_filters or {}).get("_intake") or {}
    mode = intake.get("mode") or "discovery"
    return {
        "mode": mode,
        "listing_url": intake.get("listing_url"),
        "vin": intake.get("vin"),
        "direct_promote_available": bool(
            intake.get("direct_promote_available") and mode in {"single_listing", "vin"}
        ),
    }


def _candidate_intake_mode(relevance_reasons) -> str:
    reasons = set(relevance_reasons or [])
    if "single_listing_url" in reasons:
        return "single_listing"
    if "vin_only" in reasons:
        return "vin"
    return "discovery"


def _json_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value
