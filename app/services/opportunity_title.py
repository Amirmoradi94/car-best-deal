from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityDocument, OpportunityTitleEvidence
from app.services.lien_profiles import create_lien_profile_from_title_evidence
from app.services.opportunity_documents import DOCUMENT_TYPE_LABELS, document_payload
from app.services.opportunity_promotion import normalized_visit_checklist


TITLE_SOURCE_TYPES = {
    "manual",
    "uvip",
    "ppsa_lookup",
    "ppsr_lookup",
    "seller_ownership",
    "lender_payout",
    "lien_release",
    "document_upload",
}

TITLE_CLEARANCE_STATUSES = {
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

PAYOUT_STATUSES = {
    "unknown",
    "not_required",
    "requested",
    "received",
    "paid",
    "released",
}

CLEAR_TITLE_STATUSES = {"clear", "released"}

TITLE_DOCUMENT_SOURCE_TYPES = {
    "uvip": "uvip",
    "ownership_document": "seller_ownership",
    "ppsa_report": "ppsa_lookup",
    "ppsr_report": "ppsr_lookup",
    "lender_payout_statement": "lender_payout",
    "lien_release": "lien_release",
}


class TitleEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class StoredTitleEvidence:
    evidence: OpportunityTitleEvidence
    opportunity: Opportunity


def create_title_evidence(
    session: Session,
    *,
    opportunity_id: str,
    evidence_data: dict[str, Any],
) -> StoredTitleEvidence | None:
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return None

    document = _linked_document(
        session,
        opportunity_id=opportunity.id,
        document_id=evidence_data.get("document_id"),
    )
    source_type = _validate_source_type(evidence_data.get("source_type") or "manual")
    title_status = _validate_title_status(evidence_data.get("title_clearance_status") or "unknown")
    payout_status = _validate_payout_status(evidence_data.get("payout_status") or "unknown")

    evidence = OpportunityTitleEvidence(
        opportunity_id=opportunity.id,
        source_type=source_type,
        title_clearance_status=title_status,
        provider=_blank_to_none(evidence_data.get("provider")),
        lookup_reference=_blank_to_none(evidence_data.get("lookup_reference")),
        checked_at=_blank_to_none(evidence_data.get("checked_at")),
        document_id=document.id if document is not None else None,
        seller_name=_blank_to_none(evidence_data.get("seller_name")),
        registered_owner_name=_blank_to_none(evidence_data.get("registered_owner_name")),
        ownership_verified=evidence_data.get("ownership_verified"),
        lienholder_name=_blank_to_none(evidence_data.get("lienholder_name")),
        lien_amount_cad=evidence_data.get("lien_amount_cad"),
        payout_required=evidence_data.get("payout_required"),
        payout_amount_cad=evidence_data.get("payout_amount_cad"),
        payout_due_date=_blank_to_none(evidence_data.get("payout_due_date")),
        payout_status=payout_status,
        notes=_blank_to_none(evidence_data.get("notes")),
        raw_payload=dict(evidence_data.get("raw_payload") or {}),
    )

    _apply_title_workflow_state(opportunity, evidence)
    session.add(evidence)
    session.add(opportunity)
    session.flush()
    create_lien_profile_from_title_evidence(session, evidence)
    session.commit()
    session.refresh(evidence)
    session.refresh(opportunity)
    return StoredTitleEvidence(evidence=evidence, opportunity=opportunity)


def create_title_evidence_from_document(
    session: Session,
    *,
    opportunity_id: str,
    document: OpportunityDocument,
) -> StoredTitleEvidence | None:
    source_type = TITLE_DOCUMENT_SOURCE_TYPES.get(document.document_type)
    if source_type is None:
        return None

    status = "needs_review"
    payout_required = None
    payout_status = "unknown"
    if document.document_type == "lender_payout_statement":
        status = "payout_pending"
        payout_required = True
        payout_status = "received"
    elif document.document_type == "lien_release":
        status = "released"
        payout_required = False
        payout_status = "released"

    return create_title_evidence(
        session,
        opportunity_id=opportunity_id,
        evidence_data={
            "source_type": source_type,
            "title_clearance_status": status,
            "document_id": document.id,
            "provider": DOCUMENT_TYPE_LABELS.get(document.document_type),
            "payout_required": payout_required,
            "payout_status": payout_status,
            "notes": document.notes,
            "raw_payload": {"document_type": document.document_type, "document_sha256": document.sha256},
        },
    )


def list_title_evidence(
    session: Session,
    *,
    opportunity_id: str,
) -> list[OpportunityTitleEvidence] | None:
    if session.get(Opportunity, opportunity_id) is None:
        return None
    return list(
        session.scalars(
            select(OpportunityTitleEvidence)
            .where(OpportunityTitleEvidence.opportunity_id == opportunity_id)
            .order_by(OpportunityTitleEvidence.created_at.desc(), OpportunityTitleEvidence.id.desc())
        )
    )


def latest_title_evidence(session: Session, opportunity_id: str) -> OpportunityTitleEvidence | None:
    return session.scalar(
        select(OpportunityTitleEvidence)
        .where(OpportunityTitleEvidence.opportunity_id == opportunity_id)
        .order_by(OpportunityTitleEvidence.created_at.desc(), OpportunityTitleEvidence.id.desc())
    )


def title_evidence_payload(evidence: OpportunityTitleEvidence, document: OpportunityDocument | None = None) -> dict:
    return {
        "id": evidence.id,
        "opportunity_id": evidence.opportunity_id,
        "source_type": evidence.source_type,
        "title_clearance_status": evidence.title_clearance_status,
        "provider": evidence.provider,
        "lookup_reference": evidence.lookup_reference,
        "checked_at": evidence.checked_at,
        "document_id": evidence.document_id,
        "document": document_payload(document) if document is not None else None,
        "seller_name": evidence.seller_name,
        "registered_owner_name": evidence.registered_owner_name,
        "ownership_verified": evidence.ownership_verified,
        "lienholder_name": evidence.lienholder_name,
        "lien_amount_cad": _json_number(evidence.lien_amount_cad),
        "payout_required": evidence.payout_required,
        "payout_amount_cad": _json_number(evidence.payout_amount_cad),
        "payout_due_date": evidence.payout_due_date,
        "payout_status": evidence.payout_status,
        "notes": evidence.notes,
        "raw_payload": evidence.raw_payload or {},
        "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
        "updated_at": evidence.updated_at.isoformat() if evidence.updated_at else None,
    }


def title_evidence_summary_payload(
    session: Session,
    evidence_items: list[OpportunityTitleEvidence],
) -> dict:
    latest = evidence_items[0] if evidence_items else None
    return {
        "status": latest.title_clearance_status if latest is not None else "missing",
        "count": len(evidence_items),
        "latest": _title_payload_with_document(session, latest) if latest is not None else None,
        "evidence": [_title_payload_with_document(session, item) for item in evidence_items],
    }


def title_risk_factors(evidence: OpportunityTitleEvidence | None) -> list[str]:
    if evidence is None:
        return []

    factors = []
    status = evidence.title_clearance_status
    if status == "lien_found":
        factors.append("lien reported on title evidence")
    if status in {"payout_pending", "payout_ready", "payout_paid"}:
        factors.append(f"lender payout status is {status.replace('_', ' ')}")
    if status == "blocked":
        factors.append("title clearance is blocked")
    if evidence.ownership_verified is False:
        factors.append("seller ownership not verified")
    if evidence.payout_required and evidence.payout_status not in {"paid", "released"}:
        factors.append("lender payout required before purchase")
    return factors


def _title_payload_with_document(session: Session, evidence: OpportunityTitleEvidence | None) -> dict | None:
    if evidence is None:
        return None
    document = session.get(OpportunityDocument, evidence.document_id) if evidence.document_id else None
    return title_evidence_payload(evidence, document)


def _linked_document(
    session: Session,
    *,
    opportunity_id: str,
    document_id: str | None,
) -> OpportunityDocument | None:
    if not document_id:
        return None
    document = session.get(OpportunityDocument, document_id)
    if document is None or document.opportunity_id != opportunity_id:
        raise TitleEvidenceError("Linked document not found for this opportunity")
    return document


def _apply_title_workflow_state(opportunity: Opportunity, evidence: OpportunityTitleEvidence) -> None:
    missing_key_data = list(opportunity.missing_key_data or [])
    checklist = normalized_visit_checklist(opportunity.visit_checklist)

    if evidence.title_clearance_status in CLEAR_TITLE_STATUSES:
        missing_key_data = [key for key in missing_key_data if key != "lien_verification"]
        checklist["lien_status_checked"] = True
    else:
        if "lien_verification" not in missing_key_data:
            missing_key_data.append("lien_verification")
        checklist["lien_status_checked"] = False
    if evidence.ownership_verified is True:
        checklist["vin_confirmed"] = True

    opportunity.missing_key_data = missing_key_data
    opportunity.visit_checklist = checklist


def _validate_source_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in TITLE_SOURCE_TYPES:
        raise TitleEvidenceError(f"Unsupported title evidence source type. Allowed values: {', '.join(sorted(TITLE_SOURCE_TYPES))}")
    return normalized


def _validate_title_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in TITLE_CLEARANCE_STATUSES:
        raise TitleEvidenceError(f"Unsupported title clearance status. Allowed values: {', '.join(sorted(TITLE_CLEARANCE_STATUSES))}")
    return normalized


def _validate_payout_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in PAYOUT_STATUSES:
        raise TitleEvidenceError(f"Unsupported payout status. Allowed values: {', '.join(sorted(PAYOUT_STATUSES))}")
    return normalized


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value
