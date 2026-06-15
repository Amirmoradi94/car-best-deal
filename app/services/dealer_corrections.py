from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateSnapshot, DealerCorrection, Opportunity
from app.services.opportunity_promotion import get_opportunity_with_candidate, normalized_visit_checklist
from app.services.opportunity_title import latest_title_evidence
from app.services.vehicle_history import get_latest_opportunity_history


VEHICLE_FIELDS = {"year", "make", "model", "trim", "vin", "mileage_km"}
LISTING_FIELDS = {"asking_price_cad"}
ACCIDENT_HISTORY_STATUSES = {
    "unknown",
    "none_reported",
    "accident_reported",
    "minor_damage",
    "moderate_damage",
    "major_damage",
}
LIEN_STATUSES = {
    "unknown",
    "needs_review",
    "clear",
    "lien_found",
    "payout_pending",
    "payout_ready",
    "payout_paid",
    "released",
    "blocked",
}
CORRECTABLE_FIELDS = {
    "vehicle": VEHICLE_FIELDS,
    "listing": LISTING_FIELDS,
    "history": {"accident_history_status"},
    "title": {"lien_status"},
}


class DealerCorrectionError(ValueError):
    pass


@dataclass(frozen=True)
class StoredDealerCorrection:
    correction: DealerCorrection
    opportunity: Opportunity
    candidate: CandidateSnapshot | None


def create_dealer_correction(
    session: Session,
    *,
    opportunity_id: str,
    entity_type: str,
    field_name: str,
    new_value: Any,
    reason: str | None = None,
    apply_to_future: bool = True,
) -> StoredDealerCorrection | None:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        return None

    opportunity, candidate = result
    entity_type = _normalize_key(entity_type)
    field_name = _normalize_key(field_name)
    _validate_field(entity_type, field_name)
    normalized_value = _normalize_value(entity_type, field_name, new_value)
    old_value = _current_value(
        session,
        opportunity=opportunity,
        candidate=candidate,
        entity_type=entity_type,
        field_name=field_name,
    )

    correction = DealerCorrection(
        dealer_account_id=opportunity.dealer_account_id,
        opportunity_id=opportunity.id,
        entity_type=entity_type,
        entity_id=candidate.id if candidate is not None and entity_type in {"vehicle", "listing"} else opportunity.id,
        field_name=field_name,
        old_value=old_value,
        new_value=normalized_value,
        reason=_blank_to_none(reason),
        apply_to_future=bool(apply_to_future),
    )
    _apply_workflow_state(opportunity, correction)
    session.add(correction)
    session.add(opportunity)
    session.commit()
    session.refresh(correction)
    session.refresh(opportunity)
    if candidate is not None:
        session.refresh(candidate)
    return StoredDealerCorrection(correction=correction, opportunity=opportunity, candidate=candidate)


def list_dealer_corrections(
    session: Session,
    *,
    opportunity_id: str,
) -> list[DealerCorrection] | None:
    if session.get(Opportunity, opportunity_id) is None:
        return None
    return list(
        session.scalars(
            select(DealerCorrection)
            .where(DealerCorrection.opportunity_id == opportunity_id)
            .order_by(DealerCorrection.created_at.desc(), DealerCorrection.id.desc())
        )
    )


def latest_active_correction_map(corrections: list[DealerCorrection]) -> dict[tuple[str, str], DealerCorrection]:
    latest: dict[tuple[str, str], DealerCorrection] = {}
    for correction in corrections:
        if not correction.apply_to_future:
            continue
        key = (correction.entity_type, correction.field_name)
        if key not in latest:
            latest[key] = correction
    return latest


def dealer_correction_payload(correction: DealerCorrection) -> dict:
    return {
        "id": correction.id,
        "dealer_account_id": correction.dealer_account_id,
        "opportunity_id": correction.opportunity_id,
        "entity_type": correction.entity_type,
        "entity_id": correction.entity_id,
        "field_name": correction.field_name,
        "old_value": _json_value(correction.old_value),
        "new_value": _json_value(correction.new_value),
        "reason": correction.reason,
        "apply_to_future": correction.apply_to_future,
        "created_at": correction.created_at.isoformat() if correction.created_at else None,
        "updated_at": correction.updated_at.isoformat() if correction.updated_at else None,
    }


def dealer_correction_summary_payload(corrections: list[DealerCorrection]) -> dict:
    active = latest_active_correction_map(corrections)
    latest = list(active.values())
    return {
        "count": len(corrections),
        "active_count": len(latest),
        "latest": [dealer_correction_payload(correction) for correction in latest],
        "corrections": [dealer_correction_payload(correction) for correction in corrections],
    }


def apply_vehicle_corrections(
    vehicle: dict,
    correction_map: dict[tuple[str, str], DealerCorrection],
) -> dict:
    corrected = dict(vehicle)
    for field_name in VEHICLE_FIELDS:
        correction = correction_map.get(("vehicle", field_name))
        if correction is not None:
            corrected[field_name] = _json_value(correction.new_value)
    return corrected


def apply_listing_corrections(
    listing: dict,
    correction_map: dict[tuple[str, str], DealerCorrection],
) -> dict:
    corrected = dict(listing)
    correction = correction_map.get(("listing", "asking_price_cad"))
    if correction is not None:
        corrected["asking_price_cad"] = _json_value(correction.new_value)
    return corrected


def apply_history_profile_corrections(
    history_profile: dict,
    correction_map: dict[tuple[str, str], DealerCorrection],
) -> dict:
    correction = correction_map.get(("history", "accident_history_status"))
    if correction is None:
        return history_profile

    corrected = dict(history_profile)
    status = str(correction.new_value)
    corrected["status"] = "dealer_corrected"
    corrected["accident_history_status"] = status
    if status == "none_reported":
        corrected["accident_claim_count"] = 0
        corrected["accident_claim_total_cad"] = None
        corrected["summary"] = correction.reason or "Dealer correction: no accident history reported."
    else:
        corrected["summary"] = correction.reason or f"Dealer correction: {status.replace('_', ' ')}."
    return corrected


def apply_verification_corrections(
    verification: dict,
    correction_map: dict[tuple[str, str], DealerCorrection],
) -> dict:
    corrected = dict(verification)
    history_correction = correction_map.get(("history", "accident_history_status"))
    if history_correction is not None:
        status = str(history_correction.new_value)
        corrected["history"] = {
            **dict(corrected.get("history") or {}),
            "status": "dealer_corrected",
            "source": "dealer_correction",
            "accident_history_status": status,
            "correction_id": history_correction.id,
        }

    lien_correction = correction_map.get(("title", "lien_status"))
    if lien_correction is not None:
        status = str(lien_correction.new_value)
        corrected["lien_title"] = {
            **dict(corrected.get("lien_title") or {}),
            "status": "verified" if status in {"clear", "released"} else status,
            "source": "dealer_correction",
            "title_clearance_status": status,
            "correction_id": lien_correction.id,
        }
    return corrected


def adjust_missing_key_data(
    missing_key_data: list,
    correction_map: dict[tuple[str, str], DealerCorrection],
) -> list:
    missing = list(missing_key_data or [])
    if ("history", "accident_history_status") in correction_map:
        missing = [key for key in missing if key != "vehicle_history"]
    lien = correction_map.get(("title", "lien_status"))
    if lien is not None and lien.new_value in {"clear", "released"}:
        missing = [key for key in missing if key != "lien_verification"]
    return missing


def correction_risk_factors(correction_map: dict[tuple[str, str], DealerCorrection]) -> list[str]:
    factors = []
    history = correction_map.get(("history", "accident_history_status"))
    if history is not None and history.new_value not in {"none_reported", "unknown"}:
        factors.append(f"dealer corrected accident history to {str(history.new_value).replace('_', ' ')}")
    lien = correction_map.get(("title", "lien_status"))
    if lien is not None and lien.new_value not in {"clear", "released", "unknown"}:
        factors.append(f"dealer corrected lien/title status to {str(lien.new_value).replace('_', ' ')}")
    return factors


def report_corrections_payload(corrections: list[DealerCorrection]) -> list[dict]:
    return [
        dealer_correction_payload(correction)
        for correction in latest_active_correction_map(corrections).values()
    ]


def _current_value(
    session: Session,
    *,
    opportunity: Opportunity,
    candidate: CandidateSnapshot | None,
    entity_type: str,
    field_name: str,
) -> Any:
    previous = session.scalar(
        select(DealerCorrection)
        .where(
            DealerCorrection.opportunity_id == opportunity.id,
            DealerCorrection.entity_type == entity_type,
            DealerCorrection.field_name == field_name,
            DealerCorrection.apply_to_future.is_(True),
        )
        .order_by(DealerCorrection.created_at.desc(), DealerCorrection.id.desc())
    )
    if previous is not None:
        return _json_value(previous.new_value)
    if entity_type == "vehicle" and candidate is not None:
        return _json_value(getattr(candidate, field_name))
    if entity_type == "listing" and candidate is not None:
        return _json_value(getattr(candidate, field_name))
    if entity_type == "history":
        history = get_latest_opportunity_history(session, opportunity.id)
        if history is None:
            return "unknown"
        return "accident_reported" if history.accident_claims else "none_reported"
    if entity_type == "title":
        evidence = latest_title_evidence(session, opportunity.id)
        return evidence.title_clearance_status if evidence is not None else "unknown"
    return None


def _apply_workflow_state(opportunity: Opportunity, correction: DealerCorrection) -> None:
    missing_key_data = list(opportunity.missing_key_data or [])
    checklist = normalized_visit_checklist(opportunity.visit_checklist)
    if correction.entity_type == "history" and correction.field_name == "accident_history_status":
        missing_key_data = [key for key in missing_key_data if key != "vehicle_history"]
        checklist["history_report_checked"] = True
    if (
        correction.entity_type == "title"
        and correction.field_name == "lien_status"
        and correction.new_value in {"clear", "released"}
    ):
        missing_key_data = [key for key in missing_key_data if key != "lien_verification"]
        checklist["lien_status_checked"] = True
    opportunity.missing_key_data = missing_key_data
    opportunity.visit_checklist = checklist


def _validate_field(entity_type: str, field_name: str) -> None:
    if entity_type not in CORRECTABLE_FIELDS or field_name not in CORRECTABLE_FIELDS[entity_type]:
        raise DealerCorrectionError(f"Unsupported correction field: {entity_type}.{field_name}")


def _normalize_value(entity_type: str, field_name: str, value: Any) -> Any:
    if value is None:
        raise DealerCorrectionError("Correction value is required")
    if entity_type == "vehicle" and field_name in {"year", "mileage_km"}:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise DealerCorrectionError(f"{field_name} must be a whole number") from exc
        if number < 0:
            raise DealerCorrectionError(f"{field_name} must be non-negative")
        return number
    if entity_type == "listing" and field_name == "asking_price_cad":
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise DealerCorrectionError("asking_price_cad must be numeric") from exc
        if number < 0:
            raise DealerCorrectionError("asking_price_cad must be non-negative")
        return round(number, 2)
    if entity_type == "history" and field_name == "accident_history_status":
        status = _normalize_key(str(value))
        if status not in ACCIDENT_HISTORY_STATUSES:
            raise DealerCorrectionError(f"Unsupported accident history status: {value}")
        return status
    if entity_type == "title" and field_name == "lien_status":
        status = _normalize_key(str(value))
        if status not in LIEN_STATUSES:
            raise DealerCorrectionError(f"Unsupported lien status: {value}")
        return status
    cleaned = str(value).strip()
    if not cleaned:
        raise DealerCorrectionError("Correction value is required")
    return cleaned


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value
