from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityDocument
from app.services.opportunity_promotion import normalized_visit_checklist
from app.storage.object_store import LocalObjectStore, ObjectStore


DOCUMENT_TYPE_LABELS = {
    "carfax_pdf": "CARFAX PDF",
    "uvip": "UVIP",
    "seller_document": "Seller document",
    "mechanic_quote": "Mechanic quote",
    "auction_condition_report": "Auction condition report",
    "service_invoice": "Service invoice",
    "ownership_document": "Ownership document",
    "ppsa_report": "PPSA report",
    "ppsr_report": "PPSR report",
    "lien_release": "Lien release",
    "lender_payout_statement": "Lender payout statement",
    "transport_canada_recall_report": "Transport Canada recall report",
    "oem_recall_report": "OEM recall report",
    "recall_completion_receipt": "Recall completion receipt",
    "import_compliance_document": "Import compliance document",
    "riv_inspection": "RIV inspection",
    "statement_of_compliance": "Statement of compliance",
    "cbb_valuation": "Canadian Black Book valuation",
    "manheim_mmr": "Manheim MMR",
    "openlane_auction_report": "OPENLANE auction report",
    "adesa_auction_report": "ADESA auction report",
    "traderev_bid_report": "TradeRev bid report",
    "trade_in_appraisal": "Trade-in appraisal",
    "wholesale_invoice": "Wholesale invoice",
}

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}

DEFAULT_MAX_UPLOAD_BYTES = 20_000_000


class DocumentUploadError(ValueError):
    pass


@dataclass(frozen=True)
class StoredOpportunityDocument:
    document: OpportunityDocument
    opportunity: Opportunity


def store_opportunity_document(
    session: Session,
    *,
    opportunity_id: str,
    document_type: str,
    filename: str,
    content_type: str,
    data: bytes,
    notes: str | None = None,
    object_store: ObjectStore | None = None,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> StoredOpportunityDocument | None:
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return None

    normalized_type = _normalize_document_type(document_type)
    safe_filename = _safe_filename(filename)
    normalized_content_type = _normalize_content_type(content_type)
    if not data:
        raise DocumentUploadError("Uploaded document cannot be empty")
    if len(data) > max_bytes:
        raise DocumentUploadError(f"Uploaded document exceeds {max_bytes} bytes")

    store = object_store or LocalObjectStore()
    object_key = f"opportunities/{opportunity.id}/documents/{uuid4()}-{safe_filename}"
    stored = store.put_bytes(object_key, data, normalized_content_type)
    document = OpportunityDocument(
        opportunity_id=opportunity.id,
        document_type=normalized_type,
        original_filename=safe_filename,
        content_type=normalized_content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        object_key=stored.key,
        notes=notes,
        metadata_json={"label": DOCUMENT_TYPE_LABELS[normalized_type]},
    )

    _apply_document_workflow_state(opportunity, normalized_type)
    session.add(document)
    session.add(opportunity)
    session.commit()
    session.refresh(document)
    session.refresh(opportunity)
    return StoredOpportunityDocument(document=document, opportunity=opportunity)


def list_opportunity_documents(
    session: Session,
    *,
    opportunity_id: str,
) -> list[OpportunityDocument] | None:
    if session.get(Opportunity, opportunity_id) is None:
        return None
    return list(
        session.scalars(
            select(OpportunityDocument)
            .where(OpportunityDocument.opportunity_id == opportunity_id)
            .order_by(OpportunityDocument.created_at.desc(), OpportunityDocument.id.desc())
        )
    )


def get_opportunity_document(
    session: Session,
    *,
    opportunity_id: str,
    document_id: str,
) -> OpportunityDocument | None:
    return session.scalar(
        select(OpportunityDocument).where(
            OpportunityDocument.opportunity_id == opportunity_id,
            OpportunityDocument.id == document_id,
        )
    )


def document_payload(document: OpportunityDocument) -> dict:
    return {
        "id": document.id,
        "opportunity_id": document.opportunity_id,
        "document_type": document.document_type,
        "document_label": DOCUMENT_TYPE_LABELS.get(document.document_type, document.document_type),
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "sha256": document.sha256,
        "notes": document.notes,
        "download_url": (
            f"/api/opportunities/{document.opportunity_id}/documents/{document.id}/download"
        ),
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


def document_summary_payload(documents: list[OpportunityDocument]) -> dict:
    by_type: dict[str, int] = {}
    for document in documents:
        by_type[document.document_type] = by_type.get(document.document_type, 0) + 1
    return {
        "count": len(documents),
        "by_type": by_type,
        "documents": [document_payload(document) for document in documents],
    }


def _normalize_document_type(document_type: str) -> str:
    normalized = (document_type or "").strip().lower()
    if normalized not in DOCUMENT_TYPE_LABELS:
        allowed = ", ".join(sorted(DOCUMENT_TYPE_LABELS))
        raise DocumentUploadError(f"Unsupported document type. Allowed values: {allowed}")
    return normalized


def _safe_filename(filename: str) -> str:
    name = PurePath((filename or "").strip()).name
    if not name:
        raise DocumentUploadError("Uploaded document filename is required")
    return "".join(character if character.isalnum() or character in "._- " else "_" for character in name)[:180]


def _normalize_content_type(content_type: str) -> str:
    normalized = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if normalized not in ALLOWED_CONTENT_TYPES:
        allowed = ", ".join(sorted(ALLOWED_CONTENT_TYPES))
        raise DocumentUploadError(f"Unsupported document content type. Allowed values: {allowed}")
    return normalized


def _apply_document_workflow_state(opportunity: Opportunity, document_type: str) -> None:
    missing_key_data = list(opportunity.missing_key_data or [])
    checklist = normalized_visit_checklist(opportunity.visit_checklist)

    if document_type == "carfax_pdf":
        missing_key_data = [key for key in missing_key_data if key != "vehicle_history"]
        checklist["history_report_checked"] = True
    if document_type == "service_invoice":
        checklist["service_records_requested"] = True
    if document_type in {"seller_document", "ownership_document"}:
        checklist["vin_confirmed"] = True

    opportunity.missing_key_data = missing_key_data
    opportunity.visit_checklist = checklist
