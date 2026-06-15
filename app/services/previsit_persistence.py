from decimal import Decimal
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateSnapshot, SearchRun
from app.domain.models import ScoredOpportunity
from app.scraping.contracts import SearchFilters


def persist_search_run(
    session: Session,
    *,
    search_id: str,
    name: str,
    filters: SearchFilters,
    scored_items: list[ScoredOpportunity],
    source_statuses: list[dict] | None = None,
    intake_metadata: dict | None = None,
    status: str = "completed",
    error_message: str | None = None,
) -> SearchRun:
    structured_filters = _filters_payload(filters)
    if intake_metadata:
        structured_filters["_intake"] = intake_metadata
    run = SearchRun(
        search_id=search_id,
        name=name,
        natural_language_query=filters.query,
        structured_filters=structured_filters,
        listing_limit=filters.limit,
        status=status,
        candidate_count=len(scored_items),
        source_statuses=source_statuses or [],
        error_message=error_message,
    )
    session.add(run)
    session.flush()

    for rank, scored in enumerate(scored_items, start=1):
        session.add(_candidate_snapshot(run.id, rank, scored))

    session.commit()
    session.refresh(run)
    return run


def list_search_runs(session: Session, limit: int = 50) -> list[SearchRun]:
    return list(
        session.scalars(
            select(SearchRun)
            .order_by(SearchRun.created_at.desc())
            .limit(limit)
        )
    )


def get_search_run_with_candidates(
    session: Session,
    run_id: str,
) -> tuple[SearchRun, list[CandidateSnapshot]] | None:
    run = session.get(SearchRun, run_id)
    if run is None:
        return None
    candidates = list(
        session.scalars(
            select(CandidateSnapshot)
            .where(CandidateSnapshot.search_run_id == run_id)
            .order_by(CandidateSnapshot.rank.asc())
        )
    )
    return run, candidates


def get_candidate_snapshot(
    session: Session,
    *,
    run_id: str,
    candidate_id: str,
) -> CandidateSnapshot | None:
    return session.scalar(
        select(CandidateSnapshot).where(
            CandidateSnapshot.search_run_id == run_id,
            CandidateSnapshot.id == candidate_id,
        )
    )


def update_candidate_workflow_state(
    session: Session,
    *,
    run_id: str,
    candidate_id: str,
    selected: bool | None = None,
    hidden: bool | None = None,
    seller_contact_status: str | None = None,
    seller_notes: str | None = None,
    update_seller_contact_status: bool = False,
    update_seller_notes: bool = False,
) -> CandidateSnapshot | None:
    candidate = get_candidate_snapshot(session, run_id=run_id, candidate_id=candidate_id)
    if candidate is None:
        return None
    if selected is not None:
        candidate.selected = selected
    if hidden is not None:
        candidate.hidden = hidden
    if update_seller_contact_status:
        candidate.seller_contact_status = seller_contact_status
    if update_seller_notes:
        candidate.seller_notes = seller_notes
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def _filters_payload(filters: SearchFilters) -> dict:
    payload = asdict(filters)
    return {
        key: (value.value if hasattr(value, "value") else value)
        for key, value in payload.items()
        if value is not None
    }


def _candidate_snapshot(search_run_id: str, rank: int, scored: ScoredOpportunity) -> CandidateSnapshot:
    listing = scored.listing
    vehicle = listing.vehicle
    return CandidateSnapshot(
        search_run_id=search_run_id,
        rank=rank,
        listing_id=listing.id,
        source_name=listing.source_name,
        source_url=listing.url,
        title=_title(scored),
        year=vehicle.year,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        vin=vehicle.vin,
        mileage_km=vehicle.mileage_km,
        body_style=vehicle.body_style,
        drivetrain=vehicle.drivetrain,
        asking_price_cad=listing.asking_price_cad,
        location_city=listing.location_city,
        location_province=listing.location_province,
        seller_type=listing.seller_type.value,
        deal_score=scored.deal_score,
        recommendation=scored.recommendation.value,
        is_overpriced=scored.is_overpriced,
        pricing_summary=_pricing_payload(scored),
        risk_summary=_risk_payload(scored),
        relevance_score=scored.relevance_score,
        relevance_reasons=list(scored.relevance_reasons),
        image_urls=list(listing.image_urls),
        image_risk_adjustment=listing.image_risk_adjustment,
        image_risk_reasons=list(listing.image_risk_reasons),
        confidence_by_section={
            section: confidence.value
            for section, confidence in scored.confidence_by_section.items()
        },
    )


def _title(scored: ScoredOpportunity) -> str:
    vehicle = scored.listing.vehicle
    parts = [vehicle.year, vehicle.make, vehicle.model, vehicle.trim]
    return " ".join(str(part) for part in parts if part)


def _pricing_payload(scored: ScoredOpportunity) -> dict:
    pricing = scored.pricing
    return {
        "retail_low_cad": pricing.retail_low_cad,
        "retail_mid_cad": pricing.retail_mid_cad,
        "retail_high_cad": pricing.retail_high_cad,
        "comparable_count": pricing.comparable_count,
        "estimated_reconditioning_cad": pricing.estimated_reconditioning_cad,
        "selling_costs_cad": pricing.selling_costs_cad,
        "transport_cost_cad": pricing.transport_cost_cad,
        "buying_fees_cad": pricing.buying_fees_cad,
        "capital_cost_cad": pricing.capital_cost_cad,
        "risk_reserve_cad": pricing.risk_reserve_cad,
        "target_profit_cad": pricing.target_profit_cad,
        "max_buy_price_cad": pricing.max_buy_price_cad,
        "starting_offer_cad": pricing.starting_offer_cad,
        "preliminary": pricing.preliminary,
        "comparables": [_comparable_payload(comparable) for comparable in scored.comparables],
    }


def _comparable_payload(comparable) -> dict:
    return {
        "id": comparable.id,
        "source_name": comparable.source_name,
        "source_url": comparable.url,
        "year": comparable.year,
        "make": comparable.make,
        "model": comparable.model,
        "trim": comparable.trim,
        "mileage_km": comparable.mileage_km,
        "asking_price_cad": comparable.asking_price_cad,
        "similarity_score": comparable.similarity_score,
        "included": comparable.included,
    }


def _risk_payload(scored: ScoredOpportunity) -> dict:
    return {
        "risk_score": scored.risk.risk_score,
        "risk_level": scored.risk.risk_level.value,
        "missing_verifications": list(scored.risk.missing_verifications),
        "risk_factors": list(scored.risk.risk_factors),
    }


def to_json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    return value
