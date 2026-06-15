from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CandidateSnapshot, ComparableListingModel, Opportunity, PricingAnalysisModel
from app.domain.enums import RiskTolerance, SellerType
from app.domain.models import ComparableListing, DealerSettings, ListingSnapshot, VehicleProfile
from app.services.opportunity_promotion import get_opportunity_with_candidate
from app.services.pricing import calculate_pricing


class ComparableEditingError(ValueError):
    pass


def ensure_comparables_for_opportunity(
    session: Session,
    *,
    opportunity: Opportunity,
    candidate: CandidateSnapshot | None,
) -> list[ComparableListingModel]:
    existing = _comparable_rows(session, opportunity.id)
    if existing:
        return existing
    if candidate is None:
        return []

    rows = []
    for comparable in candidate.pricing_summary.get("comparables", []) or []:
        if not isinstance(comparable, dict):
            continue
        row = ComparableListingModel(
            opportunity_id=opportunity.id,
            source_name=str(comparable.get("source_name") or "unknown"),
            source_url=comparable.get("source_url"),
            year=comparable.get("year"),
            make=comparable.get("make"),
            model=comparable.get("model"),
            trim=comparable.get("trim"),
            mileage_km=comparable.get("mileage_km"),
            asking_price_cad=float(comparable.get("asking_price_cad") or 0),
            similarity_score=float(comparable.get("similarity_score") or 0),
            included=bool(comparable.get("included", True)),
        )
        session.add(row)
        rows.append(row)
    if rows:
        session.commit()
        for row in rows:
            session.refresh(row)
    return rows


def list_opportunity_comparables(
    session: Session,
    *,
    opportunity_id: str,
) -> dict | None:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        return None
    opportunity, candidate = result
    comparables = ensure_comparables_for_opportunity(session, opportunity=opportunity, candidate=candidate)
    return _comparables_response(opportunity, candidate, comparables)


def update_comparable(
    session: Session,
    *,
    comparable_id: str,
    included: bool,
    excluded_reason: str | None = None,
) -> dict | None:
    comparable = session.get(ComparableListingModel, comparable_id)
    if comparable is None:
        return None
    result = get_opportunity_with_candidate(session, comparable.opportunity_id)
    if result is None:
        return None
    opportunity, candidate = result
    ensure_comparables_for_opportunity(session, opportunity=opportunity, candidate=candidate)

    if included is False:
        included_count = session.scalar(
            select(func.count())
            .select_from(ComparableListingModel)
            .where(
                ComparableListingModel.opportunity_id == opportunity.id,
                ComparableListingModel.included.is_(True),
                ComparableListingModel.id != comparable.id,
            )
        )
        if int(included_count or 0) < 1:
            raise ComparableEditingError("At least one comparable must remain included")

    comparable.included = bool(included)
    comparable.excluded_reason = _blank_to_none(excluded_reason) if not included else None
    session.add(comparable)
    session.commit()
    session.refresh(comparable)
    pricing = recalculate_opportunity_pricing(session, opportunity_id=opportunity.id)
    comparables = _comparable_rows(session, opportunity.id)
    return {
        **_comparables_response(opportunity, candidate, comparables),
        "updated_comparable": comparable_payload(comparable),
        "pricing_analysis": pricing_analysis_payload(pricing),
    }


def recalculate_opportunity_pricing(
    session: Session,
    *,
    opportunity_id: str,
) -> PricingAnalysisModel:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        raise ComparableEditingError("Opportunity not found")
    opportunity, candidate = result
    if candidate is None:
        raise ComparableEditingError("Opportunity has no candidate snapshot")
    comparable_rows = ensure_comparables_for_opportunity(session, opportunity=opportunity, candidate=candidate)
    included = [row for row in comparable_rows if row.included]
    if not included:
        raise ComparableEditingError("At least one comparable must remain included")

    target = _candidate_listing(candidate)
    comparables = [_domain_comparable(row) for row in comparable_rows]
    pricing_summary = dict(candidate.pricing_summary or {})
    pricing = calculate_pricing(
        target,
        comparables,
        _dealer_settings_from_pricing_summary(pricing_summary),
        estimated_reconditioning_cad=_float(pricing_summary.get("estimated_reconditioning_cad"), 900),
        selling_costs_cad=_float(pricing_summary.get("selling_costs_cad"), 500),
        transport_cost_cad=_float(pricing_summary.get("transport_cost_cad"), 250),
        buying_fees_cad=_float(pricing_summary.get("buying_fees_cad"), 0),
        capital_cost_cad=_float(pricing_summary.get("capital_cost_cad"), 250),
        risk_reserve_cad=_float(pricing_summary.get("risk_reserve_cad"), 700),
    )
    updated_summary = _pricing_payload(pricing)
    updated_summary["comparables"] = [comparable_payload(row) for row in comparable_rows]
    candidate.pricing_summary = updated_summary
    candidate.is_overpriced = bool(
        candidate.asking_price_cad is not None and float(candidate.asking_price_cad) > pricing.max_buy_price_cad
    )
    opportunity.is_overpriced = candidate.is_overpriced
    opportunity.preliminary = pricing.preliminary
    opportunity.deal_score = candidate.deal_score

    analysis = PricingAnalysisModel(
        opportunity_id=opportunity.id,
        version=_next_pricing_version(session, opportunity.id),
        status="preliminary" if pricing.preliminary else "full",
        comparable_count=pricing.comparable_count,
        retail_low_cad=pricing.retail_low_cad,
        retail_mid_cad=pricing.retail_mid_cad,
        retail_high_cad=pricing.retail_high_cad,
        max_buy_price_cad=pricing.max_buy_price_cad,
        starting_offer_cad=pricing.starting_offer_cad,
        calculation_inputs={
            "excluded_comparable_ids": [
                row.id for row in comparable_rows if not row.included
            ],
            "included_comparable_ids": [
                row.id for row in comparable_rows if row.included
            ],
            "costs": {
                "estimated_reconditioning_cad": pricing.estimated_reconditioning_cad,
                "selling_costs_cad": pricing.selling_costs_cad,
                "transport_cost_cad": pricing.transport_cost_cad,
                "buying_fees_cad": pricing.buying_fees_cad,
                "capital_cost_cad": pricing.capital_cost_cad,
                "risk_reserve_cad": pricing.risk_reserve_cad,
                "target_profit_cad": pricing.target_profit_cad,
            },
        },
    )
    session.add(candidate)
    session.add(opportunity)
    session.add(analysis)
    session.commit()
    session.refresh(candidate)
    session.refresh(opportunity)
    session.refresh(analysis)
    return analysis


def comparable_payload(comparable: ComparableListingModel) -> dict:
    return {
        "id": comparable.id,
        "opportunity_id": comparable.opportunity_id,
        "source_name": comparable.source_name,
        "source_url": comparable.source_url,
        "year": comparable.year,
        "make": comparable.make,
        "model": comparable.model,
        "trim": comparable.trim,
        "mileage_km": comparable.mileage_km,
        "asking_price_cad": _json_number(comparable.asking_price_cad),
        "similarity_score": _json_number(comparable.similarity_score),
        "included": comparable.included,
        "excluded_reason": comparable.excluded_reason,
        "created_at": comparable.created_at.isoformat() if comparable.created_at else None,
        "updated_at": comparable.updated_at.isoformat() if comparable.updated_at else None,
    }


def pricing_analysis_payload(analysis: PricingAnalysisModel) -> dict:
    return {
        "id": analysis.id,
        "opportunity_id": analysis.opportunity_id,
        "version": analysis.version,
        "status": analysis.status,
        "comparable_count": analysis.comparable_count,
        "retail_low_cad": _json_number(analysis.retail_low_cad),
        "retail_mid_cad": _json_number(analysis.retail_mid_cad),
        "retail_high_cad": _json_number(analysis.retail_high_cad),
        "max_buy_price_cad": _json_number(analysis.max_buy_price_cad),
        "starting_offer_cad": _json_number(analysis.starting_offer_cad),
        "calculation_inputs": analysis.calculation_inputs or {},
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }


def comparable_summary_payload(comparables: list[ComparableListingModel]) -> dict:
    included = [row for row in comparables if row.included]
    excluded = [row for row in comparables if not row.included]
    return {
        "count": len(comparables),
        "included_count": len(included),
        "excluded_count": len(excluded),
        "comparables": [comparable_payload(row) for row in comparables],
    }


def _comparables_response(
    opportunity: Opportunity,
    candidate: CandidateSnapshot | None,
    comparables: list[ComparableListingModel],
) -> dict:
    return {
        "opportunity_id": opportunity.id,
        "pricing_summary": dict(candidate.pricing_summary or {}) if candidate is not None else {},
        **comparable_summary_payload(comparables),
    }


def _comparable_rows(session: Session, opportunity_id: str) -> list[ComparableListingModel]:
    return list(
        session.scalars(
            select(ComparableListingModel)
            .where(ComparableListingModel.opportunity_id == opportunity_id)
            .order_by(ComparableListingModel.included.desc(), ComparableListingModel.similarity_score.desc())
        )
    )


def _candidate_listing(candidate: CandidateSnapshot) -> ListingSnapshot:
    return ListingSnapshot(
        id=candidate.listing_id,
        source_name=candidate.source_name,
        url=candidate.source_url,
        vehicle=VehicleProfile(
            year=candidate.year,
            make=candidate.make,
            model=candidate.model,
            trim=candidate.trim,
            vin=candidate.vin,
            mileage_km=candidate.mileage_km,
            drivetrain=candidate.drivetrain,
            body_style=candidate.body_style,
        ),
        asking_price_cad=_float(candidate.asking_price_cad, 0),
        location_city=candidate.location_city,
        location_province=candidate.location_province,
        seller_type=SellerType(candidate.seller_type),
        has_history="vehicle_history" not in set((candidate.risk_summary or {}).get("missing_verifications", [])),
        has_lien_verification="lien_verification" not in set(
            (candidate.risk_summary or {}).get("missing_verifications", [])
        ),
    )


def _domain_comparable(row: ComparableListingModel) -> ComparableListing:
    return ComparableListing(
        id=row.id,
        source_name=row.source_name,
        url=row.source_url or "",
        year=row.year,
        make=row.make,
        model=row.model,
        trim=row.trim,
        mileage_km=row.mileage_km,
        asking_price_cad=_float(row.asking_price_cad, 0),
        similarity_score=_float(row.similarity_score, 0),
        included=row.included,
    )


def _dealer_settings_from_pricing_summary(summary: dict) -> DealerSettings:
    return DealerSettings(
        target_profit_cad=_float(summary.get("target_profit_cad"), 2500),
        risk_tolerance=RiskTolerance.MEDIUM,
    )


def _pricing_payload(pricing) -> dict:
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
    }


def _next_pricing_version(session: Session, opportunity_id: str) -> int:
    current = session.scalar(
        select(func.max(PricingAnalysisModel.version)).where(PricingAnalysisModel.opportunity_id == opportunity_id)
    )
    return int(current or 0) + 1


def _float(value, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _json_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
