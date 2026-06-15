from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import SellerType
from app.scraping.contracts import SearchFilters
from app.services.alerts import generate_alerts_for_search_run
from app.services.dealer_settings import domain_dealer_settings, get_or_create_dealer_settings
from app.services.natural_language_search import interpret_natural_language_search
from app.services.previsit_persistence import persist_search_run
from app.services.saved_searches import get_saved_search, mark_saved_search_ran
from app.services.search_pipeline import SearchPipeline


@dataclass(frozen=True)
class SearchRunInput:
    name: str = "Ad hoc search"
    natural_language_query: str | None = None
    structured_filters: dict[str, Any] = field(default_factory=dict)
    listing_limit: int = 25
    sources: str = "both"
    max_candidates: int = 50
    listing_url: str | None = None
    vin: str | None = None


@dataclass(frozen=True)
class SearchRunExecution:
    run_id: str
    search_id: str
    intake_mode: str
    listing_url: str | None
    vin: str | None
    direct_promote_available: bool
    normalized_filters: dict
    sources: list[str]
    source_statuses: list[dict]
    ranked_opportunities: list[dict]
    interpreted_filters: dict[str, Any]
    interpretation: dict[str, Any]


async def execute_search_run(
    *,
    search_id: str,
    payload: SearchRunInput,
    session: Session,
    settings: Settings,
    saved_search_id: str | None = None,
) -> SearchRunExecution:
    interpretation = interpret_natural_language_search(
        payload.natural_language_query,
        payload.structured_filters,
    )
    filters = search_filters_from_input(payload, structured_filters=interpretation.applied_filters)
    sources = sources_from_input(payload)
    dealer_settings = domain_dealer_settings(get_or_create_dealer_settings(session))
    pipeline = SearchPipeline(
        settings_for_search_pipeline(settings, listing_url=payload.listing_url, vin=payload.vin),
        dealer_settings=dealer_settings,
    )
    try:
        if payload.listing_url:
            search_result = await pipeline.run_single_listing_analysis_with_statuses(
                payload.listing_url,
                filters,
                sources=sources,
                vin=payload.vin,
            )
        elif payload.vin:
            search_result = await pipeline.run_vin_analysis_with_statuses(
                payload.vin,
                filters,
                sources=sources,
            )
        else:
            search_result = await pipeline.run_previsit_candidate_search_with_statuses(
                filters,
                max_candidates=payload.max_candidates,
                sources=sources,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    intake_mode = intake_mode_from_input(payload)
    source_statuses = search_result.source_status_payload()
    run = persist_search_run(
        session,
        search_id=search_id,
        name=payload.name,
        filters=filters,
        scored_items=search_result.scored_items,
        source_statuses=source_statuses,
        intake_metadata=intake_metadata_from_input(payload),
    )
    if saved_search_id:
        mark_saved_search_ran(session, saved_search_id)
        saved_search = get_saved_search(session, saved_search_id)
        if saved_search is not None:
            generate_alerts_for_search_run(
                session,
                search=saved_search,
                search_run_id=run.id,
                settings=settings,
            )
    return SearchRunExecution(
        run_id=run.id,
        search_id=search_id,
        intake_mode=intake_mode,
        listing_url=payload.listing_url,
        vin=payload.vin,
        direct_promote_available=bool(intake_mode in {"single_listing", "vin"} and search_result.scored_items),
        normalized_filters=filters_payload(filters),
        sources=list(sources),
        source_statuses=source_statuses,
        ranked_opportunities=[
            opportunity_payload(search_id, scored)
            for scored in search_result.scored_items
        ],
        interpreted_filters=interpretation.interpreted_filters,
        interpretation=interpretation.payload()["interpretation"],
    )


def search_filters_from_input(
    payload: SearchRunInput,
    *,
    structured_filters: dict[str, Any] | None = None,
) -> SearchFilters:
    structured = structured_filters if structured_filters is not None else payload.structured_filters or {}
    return SearchFilters(
        query=payload.natural_language_query,
        make=structured.get("make"),
        model=structured.get("model"),
        year_min=structured.get("year_min"),
        year_max=structured.get("year_max"),
        price_min_cad=structured.get("price_min_cad"),
        price_max_cad=structured.get("price_max_cad"),
        mileage_max_km=structured.get("mileage_max_km"),
        location_city=structured.get("location_city") or "Montreal",
        location_province=structured.get("location_province") or "QC",
        radius_km=structured.get("radius_km") or 50,
        seller_type=SellerType(structured.get("seller_type") or "unknown"),
        limit=payload.listing_limit,
    )


def sources_from_input(payload: SearchRunInput) -> tuple[str, ...]:
    if payload.sources == "both":
        return ("kijiji", "autotrader")
    return (payload.sources,)


def settings_for_search_pipeline(settings: Settings, *, listing_url: str | None, vin: str | None) -> Settings:
    if settings.app_mode == "pilot" and not listing_url and not vin:
        return settings.model_copy(update={"scraping_fixture_mode": True})
    return settings


def intake_mode_from_input(payload: SearchRunInput) -> str:
    if payload.listing_url:
        return "single_listing"
    if payload.vin:
        return "vin"
    return "discovery"


def filters_payload(filters: SearchFilters) -> dict:
    return {
        "query": filters.query,
        "make": filters.make,
        "model": filters.model,
        "year_min": filters.year_min,
        "year_max": filters.year_max,
        "price_min_cad": filters.price_min_cad,
        "price_max_cad": filters.price_max_cad,
        "mileage_max_km": filters.mileage_max_km,
        "location_city": filters.location_city,
        "location_province": filters.location_province,
        "radius_km": filters.radius_km,
        "seller_type": filters.seller_type.value,
        "limit": filters.limit,
    }


def intake_metadata_from_input(payload: SearchRunInput) -> dict:
    mode = intake_mode_from_input(payload)
    return {
        "mode": mode,
        "listing_url": payload.listing_url,
        "vin": payload.vin,
        "direct_promote_available": mode in {"single_listing", "vin"},
    }


def opportunity_payload(search_id: str, scored) -> dict:
    intake_mode = candidate_intake_mode(scored.relevance_reasons)
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


def candidate_intake_mode(relevance_reasons: list[str]) -> str:
    if "single_listing_url" in relevance_reasons:
        return "single_listing"
    if "vin_only" in relevance_reasons:
        return "vin"
    return "discovery"
