from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateSnapshot, Opportunity
from app.domain.enums import OpportunityStage
from app.services.previsit_persistence import get_candidate_snapshot
from app.services.saved_searches import get_or_create_default_dealer


VISIT_CHECKLIST_DEFAULTS = {
    "vin_confirmed": False,
    "service_records_requested": False,
    "lien_status_checked": False,
    "history_report_checked": False,
    "extra_photos_requested": False,
    "visit_appointment_set": False,
}


def promote_candidate_to_opportunity(
    session: Session,
    *,
    run_id: str,
    candidate_id: str,
) -> tuple[Opportunity, CandidateSnapshot] | None:
    candidate = get_candidate_snapshot(session, run_id=run_id, candidate_id=candidate_id)
    if candidate is None:
        return None

    if candidate.opportunity_id:
        opportunity = session.get(Opportunity, candidate.opportunity_id)
        if opportunity is not None:
            return opportunity, candidate

    dealer = get_or_create_default_dealer(session)
    risk_summary = candidate.risk_summary or {}
    pricing_summary = candidate.pricing_summary or {}
    opportunity = Opportunity(
        dealer_account_id=dealer.id,
        stage=OpportunityStage.CANDIDATE.value,
        deal_score=candidate.deal_score,
        preliminary=bool(pricing_summary.get("preliminary", True)),
        missing_key_data=list(risk_summary.get("missing_verifications", [])),
        is_overpriced=candidate.is_overpriced,
        candidate_selected=True,
        seller_contact_status=candidate.seller_contact_status,
        seller_notes=candidate.seller_notes,
        visit_checklist=_initial_visit_checklist(candidate),
    )
    session.add(opportunity)
    session.flush()

    candidate.selected = True
    candidate.opportunity_id = opportunity.id
    session.add(candidate)
    session.commit()
    session.refresh(opportunity)
    session.refresh(candidate)
    return opportunity, candidate


def list_opportunities(session: Session, limit: int = 50) -> list[tuple[Opportunity, CandidateSnapshot | None]]:
    opportunities = list(
        session.scalars(
            select(Opportunity)
            .order_by(Opportunity.created_at.desc())
            .limit(limit)
        )
    )
    return [(opportunity, _candidate_for_opportunity(session, opportunity.id)) for opportunity in opportunities]


def get_opportunity_with_candidate(
    session: Session,
    opportunity_id: str,
) -> tuple[Opportunity, CandidateSnapshot | None] | None:
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return None
    return opportunity, _candidate_for_opportunity(session, opportunity.id)


def update_opportunity_stage(
    session: Session,
    *,
    opportunity_id: str,
    stage: OpportunityStage,
    override_missing_data_warning: bool = False,
) -> tuple[Opportunity, CandidateSnapshot | None, str | None] | None:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        return None

    opportunity, candidate = result
    stage_update_warning = None
    next_stage = stage.value
    if (
        stage == OpportunityStage.READY_TO_VISIT
        and opportunity.missing_key_data
        and not override_missing_data_warning
    ):
        next_stage = OpportunityStage.NEEDS_DATA.value
        stage_update_warning = "missing_key_data_requires_override"

    opportunity.stage = next_stage
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    if candidate is not None:
        session.refresh(candidate)
    return opportunity, candidate, stage_update_warning


def update_opportunity_contact(
    session: Session,
    *,
    opportunity_id: str,
    seller_contact_status: str | None = None,
    seller_notes: str | None = None,
    update_seller_contact_status: bool = False,
    update_seller_notes: bool = False,
) -> tuple[Opportunity, CandidateSnapshot | None] | None:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        return None

    opportunity, candidate = result
    if update_seller_contact_status:
        opportunity.seller_contact_status = seller_contact_status
        if candidate is not None:
            candidate.seller_contact_status = seller_contact_status
    if update_seller_notes:
        opportunity.seller_notes = seller_notes
        if candidate is not None:
            candidate.seller_notes = seller_notes

    session.add(opportunity)
    if candidate is not None:
        session.add(candidate)
    session.commit()
    session.refresh(opportunity)
    if candidate is not None:
        session.refresh(candidate)
    return opportunity, candidate


def update_opportunity_visit_checklist(
    session: Session,
    *,
    opportunity_id: str,
    checklist_patch: dict[str, bool],
) -> tuple[Opportunity, CandidateSnapshot | None] | None:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        return None

    opportunity, candidate = result
    checklist = normalized_visit_checklist(opportunity.visit_checklist)
    for key, value in checklist_patch.items():
        if key in VISIT_CHECKLIST_DEFAULTS:
            checklist[key] = bool(value)
    opportunity.visit_checklist = checklist
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    if candidate is not None:
        session.refresh(candidate)
    return opportunity, candidate


def opportunity_payload(opportunity: Opportunity, candidate: CandidateSnapshot | None = None) -> dict:
    readiness_warnings = opportunity_readiness_warnings(opportunity)
    payload = {
        "id": opportunity.id,
        "stage": opportunity.stage,
        "deal_score": _json_number(opportunity.deal_score),
        "preliminary": opportunity.preliminary,
        "missing_key_data": opportunity.missing_key_data,
        "is_overpriced": opportunity.is_overpriced,
        "candidate_selected": opportunity.candidate_selected,
        "seller_contact_status": opportunity.seller_contact_status,
        "seller_notes": opportunity.seller_notes,
        "visit_checklist": normalized_visit_checklist(opportunity.visit_checklist),
        "readiness_warnings": readiness_warnings,
        "ready_to_visit_blocked": bool(
            readiness_warnings and opportunity.stage != OpportunityStage.READY_TO_VISIT.value
        ),
        "created_at": opportunity.created_at.isoformat() if opportunity.created_at else None,
        "updated_at": opportunity.updated_at.isoformat() if opportunity.updated_at else None,
        "candidate": None,
    }
    if candidate is not None:
        payload["candidate"] = candidate_summary_payload(candidate)
    return payload


def default_visit_checklist() -> dict[str, bool]:
    return dict(VISIT_CHECKLIST_DEFAULTS)


def _initial_visit_checklist(candidate: CandidateSnapshot) -> dict[str, bool]:
    checklist = default_visit_checklist()
    if candidate.vin:
        checklist["vin_confirmed"] = True
    return checklist


def normalized_visit_checklist(checklist: dict | None) -> dict[str, bool]:
    normalized = default_visit_checklist()
    for key, value in (checklist or {}).items():
        if key in normalized:
            normalized[key] = bool(value)
    return normalized


def opportunity_readiness_warnings(opportunity: Opportunity) -> list[dict]:
    warnings = []
    missing_key_data = opportunity.missing_key_data or []
    if missing_key_data:
        warnings.append(
            {
                "code": "missing_key_data",
                "message": "Key vehicle data is missing before a visit decision.",
                "fields": missing_key_data,
            }
        )
    return warnings


def candidate_summary_payload(candidate: CandidateSnapshot) -> dict:
    return {
        "id": candidate.id,
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
        "asking_price_cad": _json_number(candidate.asking_price_cad),
        "location_city": candidate.location_city,
        "location_province": candidate.location_province,
        "recommendation": candidate.recommendation,
        "pricing_summary": candidate.pricing_summary,
        "risk_summary": candidate.risk_summary,
        "image_count": len(candidate.image_urls),
        "selected": candidate.selected,
        "hidden": candidate.hidden,
        "seller_contact_status": candidate.seller_contact_status,
        "seller_notes": candidate.seller_notes,
        "opportunity_id": candidate.opportunity_id,
    }


def _candidate_for_opportunity(session: Session, opportunity_id: str) -> CandidateSnapshot | None:
    return session.scalar(
        select(CandidateSnapshot)
        .where(CandidateSnapshot.opportunity_id == opportunity_id)
        .order_by(CandidateSnapshot.created_at.desc())
    )


def _json_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value
