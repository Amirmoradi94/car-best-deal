from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityDocument, OpportunityRecallComplianceEvidence
from app.services.opportunity_documents import DOCUMENT_TYPE_LABELS, document_payload


RECALL_COMPLIANCE_MISSING_KEY = "recall_compliance"

RECALL_SOURCE_TYPES = {
    "manual",
    "transport_canada",
    "oem_portal",
    "dealer_service",
    "import_compliance",
    "riv",
    "document_upload",
}

RECALL_STATUSES = {
    "unknown",
    "not_checked",
    "no_open_recalls",
    "open_recall",
    "incomplete",
    "completed",
    "needs_review",
}

COMPLIANCE_STATUSES = {
    "unknown",
    "not_applicable",
    "needs_review",
    "compliant",
    "non_compliant",
    "needs_inspection",
    "import_pending",
    "blocked",
}

REMEDY_STATUSES = {
    "unknown",
    "not_required",
    "required",
    "scheduled",
    "completed",
    "parts_unavailable",
}

CLEAR_RECALL_STATUSES = {"no_open_recalls", "completed"}
CLEAR_COMPLIANCE_STATUSES = {"not_applicable", "compliant"}
BLOCKING_RECALL_STATUSES = {"open_recall", "incomplete", "needs_review", "not_checked", "unknown"}
BLOCKING_COMPLIANCE_STATUSES = {"non_compliant", "needs_inspection", "import_pending", "blocked"}
BLOCKING_REMEDY_STATUSES = {"required", "scheduled", "parts_unavailable"}

RECALL_DOCUMENT_SOURCE_TYPES = {
    "transport_canada_recall_report": "transport_canada",
    "oem_recall_report": "oem_portal",
    "recall_completion_receipt": "dealer_service",
    "import_compliance_document": "import_compliance",
    "riv_inspection": "riv",
    "statement_of_compliance": "import_compliance",
}


class RecallComplianceError(ValueError):
    pass


@dataclass(frozen=True)
class StoredRecallComplianceEvidence:
    evidence: OpportunityRecallComplianceEvidence
    opportunity: Opportunity


def create_recall_compliance_evidence(
    session: Session,
    *,
    opportunity_id: str,
    evidence_data: dict[str, Any],
) -> StoredRecallComplianceEvidence | None:
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return None

    document = _linked_document(
        session,
        opportunity_id=opportunity.id,
        document_id=evidence_data.get("document_id"),
    )
    source_type = _validate_source_type(evidence_data.get("source_type") or "manual")
    recall_status = _validate_recall_status(evidence_data.get("recall_status") or "unknown")
    compliance_status = _validate_compliance_status(evidence_data.get("compliance_status") or "unknown")
    remedy_status = _validate_remedy_status(evidence_data.get("remedy_status") or "unknown")

    evidence = OpportunityRecallComplianceEvidence(
        opportunity_id=opportunity.id,
        source_type=source_type,
        recall_status=recall_status,
        compliance_status=compliance_status,
        provider=_blank_to_none(evidence_data.get("provider")),
        lookup_reference=_blank_to_none(evidence_data.get("lookup_reference")),
        checked_at=_blank_to_none(evidence_data.get("checked_at")),
        document_id=document.id if document is not None else None,
        campaign_number=_blank_to_none(evidence_data.get("campaign_number")),
        campaign_description=_blank_to_none(evidence_data.get("campaign_description")),
        remedy_status=remedy_status,
        completion_date=_blank_to_none(evidence_data.get("completion_date")),
        import_country=_blank_to_none(evidence_data.get("import_country")),
        import_form=_blank_to_none(evidence_data.get("import_form")),
        riv_case_number=_blank_to_none(evidence_data.get("riv_case_number")),
        inspection_required=evidence_data.get("inspection_required"),
        inspection_deadline=_blank_to_none(evidence_data.get("inspection_deadline")),
        notes=_blank_to_none(evidence_data.get("notes")),
        raw_payload=dict(evidence_data.get("raw_payload") or {}),
    )

    _apply_recall_compliance_workflow_state(opportunity, evidence)
    session.add(evidence)
    session.add(opportunity)
    session.commit()
    session.refresh(evidence)
    session.refresh(opportunity)
    return StoredRecallComplianceEvidence(evidence=evidence, opportunity=opportunity)


def create_recall_compliance_from_document(
    session: Session,
    *,
    opportunity_id: str,
    document: OpportunityDocument,
) -> StoredRecallComplianceEvidence | None:
    source_type = RECALL_DOCUMENT_SOURCE_TYPES.get(document.document_type)
    if source_type is None:
        return None

    recall_status = "needs_review"
    compliance_status = "unknown"
    remedy_status = "unknown"
    if document.document_type == "recall_completion_receipt":
        recall_status = "completed"
        compliance_status = "not_applicable"
        remedy_status = "completed"
    elif document.document_type in {"import_compliance_document", "riv_inspection", "statement_of_compliance"}:
        recall_status = "unknown"
        compliance_status = "needs_inspection" if document.document_type == "riv_inspection" else "needs_review"
        if document.document_type == "statement_of_compliance":
            compliance_status = "compliant"

    return create_recall_compliance_evidence(
        session,
        opportunity_id=opportunity_id,
        evidence_data={
            "source_type": source_type,
            "recall_status": recall_status,
            "compliance_status": compliance_status,
            "remedy_status": remedy_status,
            "document_id": document.id,
            "provider": DOCUMENT_TYPE_LABELS.get(document.document_type),
            "notes": document.notes,
            "raw_payload": {"document_type": document.document_type, "document_sha256": document.sha256},
        },
    )


def list_recall_compliance_evidence(
    session: Session,
    *,
    opportunity_id: str,
) -> list[OpportunityRecallComplianceEvidence] | None:
    if session.get(Opportunity, opportunity_id) is None:
        return None
    return list(
        session.scalars(
            select(OpportunityRecallComplianceEvidence)
            .where(OpportunityRecallComplianceEvidence.opportunity_id == opportunity_id)
            .order_by(
                OpportunityRecallComplianceEvidence.created_at.desc(),
                OpportunityRecallComplianceEvidence.id.desc(),
            )
        )
    )


def latest_recall_compliance_evidence(
    session: Session,
    opportunity_id: str,
) -> OpportunityRecallComplianceEvidence | None:
    return session.scalar(
        select(OpportunityRecallComplianceEvidence)
        .where(OpportunityRecallComplianceEvidence.opportunity_id == opportunity_id)
        .order_by(
            OpportunityRecallComplianceEvidence.created_at.desc(),
            OpportunityRecallComplianceEvidence.id.desc(),
        )
    )


def recall_compliance_payload(
    evidence: OpportunityRecallComplianceEvidence,
    document: OpportunityDocument | None = None,
) -> dict:
    return {
        "id": evidence.id,
        "opportunity_id": evidence.opportunity_id,
        "source_type": evidence.source_type,
        "recall_status": evidence.recall_status,
        "compliance_status": evidence.compliance_status,
        "provider": evidence.provider,
        "lookup_reference": evidence.lookup_reference,
        "checked_at": evidence.checked_at,
        "document_id": evidence.document_id,
        "document": document_payload(document) if document is not None else None,
        "campaign_number": evidence.campaign_number,
        "campaign_description": evidence.campaign_description,
        "remedy_status": evidence.remedy_status,
        "completion_date": evidence.completion_date,
        "import_country": evidence.import_country,
        "import_form": evidence.import_form,
        "riv_case_number": evidence.riv_case_number,
        "inspection_required": evidence.inspection_required,
        "inspection_deadline": evidence.inspection_deadline,
        "notes": evidence.notes,
        "raw_payload": evidence.raw_payload or {},
        "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
        "updated_at": evidence.updated_at.isoformat() if evidence.updated_at else None,
    }


def recall_compliance_summary_payload(
    session: Session,
    evidence_items: list[OpportunityRecallComplianceEvidence],
) -> dict:
    latest = evidence_items[0] if evidence_items else None
    return {
        "status": _summary_status(latest),
        "count": len(evidence_items),
        "latest": _recall_payload_with_document(session, latest) if latest is not None else None,
        "evidence": [_recall_payload_with_document(session, item) for item in evidence_items],
    }


def recall_compliance_risk_factors(evidence: OpportunityRecallComplianceEvidence | None) -> list[str]:
    if evidence is None:
        return []

    factors = []
    if evidence.recall_status == "open_recall":
        factors.append("open recall reported")
    if evidence.recall_status == "incomplete":
        factors.append("recall completion is incomplete")
    if evidence.recall_status == "needs_review":
        factors.append("recall evidence needs review")
    if evidence.remedy_status in BLOCKING_REMEDY_STATUSES:
        factors.append(f"recall remedy status is {evidence.remedy_status.replace('_', ' ')}")
    if evidence.compliance_status == "non_compliant":
        factors.append("Canadian import compliance is not cleared")
    if evidence.compliance_status == "needs_inspection":
        factors.append("RIV or import compliance inspection is required")
    if evidence.compliance_status == "import_pending":
        factors.append("Canadian import compliance is pending")
    if evidence.compliance_status == "blocked":
        factors.append("Canadian import compliance is blocked")
    return factors


def is_recall_compliance_clear(evidence: OpportunityRecallComplianceEvidence | None) -> bool:
    if evidence is None:
        return False
    return (
        evidence.recall_status in CLEAR_RECALL_STATUSES
        and evidence.compliance_status in CLEAR_COMPLIANCE_STATUSES
        and evidence.remedy_status not in BLOCKING_REMEDY_STATUSES
    )


def _recall_payload_with_document(
    session: Session,
    evidence: OpportunityRecallComplianceEvidence | None,
) -> dict | None:
    if evidence is None:
        return None
    document = session.get(OpportunityDocument, evidence.document_id) if evidence.document_id else None
    return recall_compliance_payload(evidence, document)


def _summary_status(evidence: OpportunityRecallComplianceEvidence | None) -> str:
    if evidence is None:
        return "missing"
    if is_recall_compliance_clear(evidence):
        return "clear"
    if evidence.recall_status in {"open_recall", "incomplete"}:
        return evidence.recall_status
    if evidence.compliance_status in BLOCKING_COMPLIANCE_STATUSES:
        return evidence.compliance_status
    if evidence.recall_status == "needs_review" or evidence.compliance_status == "needs_review":
        return "needs_review"
    return evidence.recall_status if evidence.recall_status != "unknown" else evidence.compliance_status


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
        raise RecallComplianceError("Linked document not found for this opportunity")
    return document


def _apply_recall_compliance_workflow_state(
    opportunity: Opportunity,
    evidence: OpportunityRecallComplianceEvidence,
) -> None:
    missing_key_data = list(opportunity.missing_key_data or [])
    if is_recall_compliance_clear(evidence):
        missing_key_data = [key for key in missing_key_data if key != RECALL_COMPLIANCE_MISSING_KEY]
    else:
        if RECALL_COMPLIANCE_MISSING_KEY not in missing_key_data:
            missing_key_data.append(RECALL_COMPLIANCE_MISSING_KEY)
    opportunity.missing_key_data = missing_key_data


def _validate_source_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in RECALL_SOURCE_TYPES:
        raise RecallComplianceError(
            f"Unsupported recall/compliance source type. Allowed values: {', '.join(sorted(RECALL_SOURCE_TYPES))}"
        )
    return normalized


def _validate_recall_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in RECALL_STATUSES:
        raise RecallComplianceError(
            f"Unsupported recall status. Allowed values: {', '.join(sorted(RECALL_STATUSES))}"
        )
    return normalized


def _validate_compliance_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in COMPLIANCE_STATUSES:
        raise RecallComplianceError(
            f"Unsupported compliance status. Allowed values: {', '.join(sorted(COMPLIANCE_STATUSES))}"
        )
    return normalized


def _validate_remedy_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in REMEDY_STATUSES:
        raise RecallComplianceError(
            f"Unsupported remedy status. Allowed values: {', '.join(sorted(REMEDY_STATUSES))}"
        )
    return normalized


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
