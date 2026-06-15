from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityHistoryProfile
from app.services.opportunity_promotion import get_opportunity_with_candidate, normalized_visit_checklist


def upsert_opportunity_history(
    session: Session,
    *,
    opportunity_id: str,
    history_data: dict[str, Any],
) -> tuple[OpportunityHistoryProfile, Opportunity, object | None] | None:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        return None

    opportunity, candidate = result
    profile = get_latest_opportunity_history(session, opportunity_id)
    if profile is None:
        profile = OpportunityHistoryProfile(opportunity_id=opportunity.id)

    profile.source_type = history_data.get("source_type") or "manual"
    profile.source_name = history_data.get("source_name")
    profile.report_identifier = history_data.get("report_identifier")
    profile.title_brand = history_data.get("title_brand") or "unknown"
    profile.accident_claims = list(history_data.get("accident_claims") or [])
    profile.registration_events = list(history_data.get("registration_events") or [])
    profile.owners_count = history_data.get("owners_count")
    profile.odometer_records = list(history_data.get("odometer_records") or [])
    profile.odometer_issue = history_data.get("odometer_issue")
    profile.service_records_count = history_data.get("service_records_count")
    profile.service_records = list(history_data.get("service_records") or [])
    profile.import_history = list(history_data.get("import_history") or [])
    profile.salvage_status = history_data.get("salvage_status") or "unknown"
    profile.flood_status = history_data.get("flood_status") or "unknown"
    profile.fire_status = history_data.get("fire_status") or "unknown"
    profile.theft_status = history_data.get("theft_status") or "unknown"
    profile.summary = history_data.get("summary")
    profile.raw_payload = dict(history_data.get("raw_payload") or {})

    missing_key_data = [
        key for key in list(opportunity.missing_key_data or []) if key != "vehicle_history"
    ]
    opportunity.missing_key_data = missing_key_data
    checklist = normalized_visit_checklist(opportunity.visit_checklist)
    checklist["history_report_checked"] = True
    opportunity.visit_checklist = checklist

    session.add(profile)
    session.add(opportunity)
    session.commit()
    session.refresh(profile)
    session.refresh(opportunity)
    if candidate is not None:
        session.refresh(candidate)
    return profile, opportunity, candidate


def list_opportunity_history(
    session: Session,
    *,
    opportunity_id: str,
) -> list[OpportunityHistoryProfile] | None:
    if session.get(Opportunity, opportunity_id) is None:
        return None
    return list(
        session.scalars(
            select(OpportunityHistoryProfile)
            .where(OpportunityHistoryProfile.opportunity_id == opportunity_id)
            .order_by(OpportunityHistoryProfile.created_at.desc(), OpportunityHistoryProfile.id.desc())
        )
    )


def get_latest_opportunity_history(
    session: Session,
    opportunity_id: str,
) -> OpportunityHistoryProfile | None:
    return session.scalar(
        select(OpportunityHistoryProfile)
        .where(OpportunityHistoryProfile.opportunity_id == opportunity_id)
        .order_by(OpportunityHistoryProfile.created_at.desc(), OpportunityHistoryProfile.id.desc())
    )


def history_payload(profile: OpportunityHistoryProfile) -> dict:
    return {
        "id": profile.id,
        "opportunity_id": profile.opportunity_id,
        "source_type": profile.source_type,
        "source_name": profile.source_name,
        "report_identifier": profile.report_identifier,
        "title_brand": profile.title_brand,
        "accident_claims": list(profile.accident_claims or []),
        "registration_events": list(profile.registration_events or []),
        "owners_count": profile.owners_count,
        "odometer_records": list(profile.odometer_records or []),
        "odometer_issue": profile.odometer_issue,
        "service_records_count": profile.service_records_count,
        "service_records": list(profile.service_records or []),
        "import_history": list(profile.import_history or []),
        "salvage_status": profile.salvage_status,
        "flood_status": profile.flood_status,
        "fire_status": profile.fire_status,
        "theft_status": profile.theft_status,
        "summary": profile.summary,
        "raw_payload": profile.raw_payload or {},
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def history_report_payload(profile: OpportunityHistoryProfile | None) -> dict:
    if profile is None:
        return {
            "status": "missing",
            "source_type": None,
            "source_name": None,
            "report_identifier": None,
            "title_brand": "unknown",
            "accident_claim_count": 0,
            "accident_claim_total_cad": None,
            "owners_count": None,
            "odometer_record_count": 0,
            "odometer_issue": None,
            "service_records_count": None,
            "registration_event_count": 0,
            "import_event_count": 0,
            "salvage_status": "unknown",
            "flood_status": "unknown",
            "fire_status": "unknown",
            "theft_status": "unknown",
            "summary": None,
        }

    accident_claims = list(profile.accident_claims or [])
    total_claims = _sum_claim_amounts(accident_claims)
    return {
        "status": "provided",
        "id": profile.id,
        "source_type": profile.source_type,
        "source_name": profile.source_name,
        "report_identifier": profile.report_identifier,
        "title_brand": profile.title_brand,
        "accident_claim_count": len(accident_claims),
        "accident_claim_total_cad": total_claims,
        "accident_claims": accident_claims,
        "registration_events": list(profile.registration_events or []),
        "registration_event_count": len(profile.registration_events or []),
        "owners_count": profile.owners_count,
        "odometer_records": list(profile.odometer_records or []),
        "odometer_record_count": len(profile.odometer_records or []),
        "odometer_issue": profile.odometer_issue,
        "service_records_count": profile.service_records_count,
        "service_records": list(profile.service_records or []),
        "import_history": list(profile.import_history or []),
        "import_event_count": len(profile.import_history or []),
        "salvage_status": profile.salvage_status,
        "flood_status": profile.flood_status,
        "fire_status": profile.fire_status,
        "theft_status": profile.theft_status,
        "summary": profile.summary,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def history_risk_factors(profile: OpportunityHistoryProfile | None) -> list[str]:
    if profile is None:
        return []

    factors = []
    title_brand = (profile.title_brand or "unknown").lower()
    if title_brand not in {"clean", "unknown"}:
        factors.append(f"title brand reported as {title_brand}")
    for key, value in [
        ("salvage", profile.salvage_status),
        ("flood", profile.flood_status),
        ("fire", profile.fire_status),
        ("theft", profile.theft_status),
    ]:
        if (value or "unknown").lower() == "reported":
            factors.append(f"{key} history reported")
    if profile.odometer_issue is True:
        factors.append("odometer issue reported")
    accident_claims = list(profile.accident_claims or [])
    if accident_claims:
        factors.append(f"{len(accident_claims)} accident claim(s) reported")
    if profile.import_history:
        factors.append("import history reported")
    return factors


def _sum_claim_amounts(accident_claims: list[dict]) -> float | None:
    total = 0.0
    found = False
    for claim in accident_claims:
        amount = claim.get("amount_cad") if isinstance(claim, dict) else None
        if amount is None:
            continue
        if isinstance(amount, Decimal):
            amount = float(amount)
        total += float(amount)
        found = True
    return round(total, 2) if found else None
