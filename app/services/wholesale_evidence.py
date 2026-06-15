from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityDocument, OpportunityWholesaleEvidence
from app.services.opportunity_documents import DOCUMENT_TYPE_LABELS, document_payload


WHOLESALE_SOURCE_TYPES = {
    "manual",
    "canadian_black_book",
    "manheim_mmr",
    "openlane",
    "adesa",
    "traderev",
    "auction_report",
    "trade_in_appraisal",
    "document_upload",
}

CONDITION_GRADES = {
    "unknown",
    "rough",
    "average",
    "clean",
    "extra_clean",
    "auction_1",
    "auction_2",
    "auction_3",
    "auction_4",
    "auction_5",
}

WHOLESALE_DOCUMENT_SOURCE_TYPES = {
    "cbb_valuation": "canadian_black_book",
    "manheim_mmr": "manheim_mmr",
    "openlane_auction_report": "openlane",
    "adesa_auction_report": "adesa",
    "traderev_bid_report": "traderev",
    "trade_in_appraisal": "trade_in_appraisal",
    "wholesale_invoice": "auction_report",
    "auction_condition_report": "auction_report",
}


class WholesaleEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class StoredWholesaleEvidence:
    evidence: OpportunityWholesaleEvidence
    opportunity: Opportunity


def create_wholesale_evidence(
    session: Session,
    *,
    opportunity_id: str,
    evidence_data: dict[str, Any],
) -> StoredWholesaleEvidence | None:
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return None

    document = _linked_document(
        session,
        opportunity_id=opportunity.id,
        document_id=evidence_data.get("document_id"),
    )
    source_type = _validate_source_type(evidence_data.get("source_type") or "manual")
    condition_grade = _validate_condition_grade(evidence_data.get("condition_grade") or "unknown")

    evidence = OpportunityWholesaleEvidence(
        opportunity_id=opportunity.id,
        source_type=source_type,
        provider=_blank_to_none(evidence_data.get("provider")),
        lookup_reference=_blank_to_none(evidence_data.get("lookup_reference")),
        checked_at=_blank_to_none(evidence_data.get("checked_at")),
        document_id=document.id if document is not None else None,
        region=_blank_to_none(evidence_data.get("region")),
        wholesale_low_cad=evidence_data.get("wholesale_low_cad"),
        wholesale_avg_cad=evidence_data.get("wholesale_avg_cad"),
        wholesale_high_cad=evidence_data.get("wholesale_high_cad"),
        trade_in_value_cad=evidence_data.get("trade_in_value_cad"),
        retail_value_cad=evidence_data.get("retail_value_cad"),
        auction_sale_low_cad=evidence_data.get("auction_sale_low_cad"),
        auction_sale_avg_cad=evidence_data.get("auction_sale_avg_cad"),
        auction_sale_high_cad=evidence_data.get("auction_sale_high_cad"),
        bid_count=evidence_data.get("bid_count"),
        bidder_count=evidence_data.get("bidder_count"),
        high_bid_cad=evidence_data.get("high_bid_cad"),
        sale_price_cad=evidence_data.get("sale_price_cad"),
        reserve_price_cad=evidence_data.get("reserve_price_cad"),
        condition_grade=condition_grade,
        condition_score=evidence_data.get("condition_score"),
        condition_notes=_blank_to_none(evidence_data.get("condition_notes")),
        buyer_fee_cad=evidence_data.get("buyer_fee_cad"),
        transport_estimate_cad=evidence_data.get("transport_estimate_cad"),
        reconditioning_estimate_cad=evidence_data.get("reconditioning_estimate_cad"),
        notes=_blank_to_none(evidence_data.get("notes")),
        raw_payload=dict(evidence_data.get("raw_payload") or {}),
    )

    session.add(evidence)
    session.commit()
    session.refresh(evidence)
    session.refresh(opportunity)
    return StoredWholesaleEvidence(evidence=evidence, opportunity=opportunity)


def create_wholesale_evidence_from_document(
    session: Session,
    *,
    opportunity_id: str,
    document: OpportunityDocument,
) -> StoredWholesaleEvidence | None:
    source_type = WHOLESALE_DOCUMENT_SOURCE_TYPES.get(document.document_type)
    if source_type is None:
        return None

    return create_wholesale_evidence(
        session,
        opportunity_id=opportunity_id,
        evidence_data={
            "source_type": source_type,
            "document_id": document.id,
            "provider": DOCUMENT_TYPE_LABELS.get(document.document_type),
            "condition_grade": "unknown",
            "notes": document.notes,
            "raw_payload": {"document_type": document.document_type, "document_sha256": document.sha256},
        },
    )


def list_wholesale_evidence(
    session: Session,
    *,
    opportunity_id: str,
) -> list[OpportunityWholesaleEvidence] | None:
    if session.get(Opportunity, opportunity_id) is None:
        return None
    return list(
        session.scalars(
            select(OpportunityWholesaleEvidence)
            .where(OpportunityWholesaleEvidence.opportunity_id == opportunity_id)
            .order_by(OpportunityWholesaleEvidence.created_at.desc(), OpportunityWholesaleEvidence.id.desc())
        )
    )


def latest_wholesale_evidence(session: Session, opportunity_id: str) -> OpportunityWholesaleEvidence | None:
    return session.scalar(
        select(OpportunityWholesaleEvidence)
        .where(OpportunityWholesaleEvidence.opportunity_id == opportunity_id)
        .order_by(OpportunityWholesaleEvidence.created_at.desc(), OpportunityWholesaleEvidence.id.desc())
    )


def wholesale_evidence_payload(
    evidence: OpportunityWholesaleEvidence,
    document: OpportunityDocument | None = None,
) -> dict:
    return {
        "id": evidence.id,
        "opportunity_id": evidence.opportunity_id,
        "source_type": evidence.source_type,
        "provider": evidence.provider,
        "lookup_reference": evidence.lookup_reference,
        "checked_at": evidence.checked_at,
        "document_id": evidence.document_id,
        "document": document_payload(document) if document is not None else None,
        "region": evidence.region,
        "wholesale_low_cad": _json_number(evidence.wholesale_low_cad),
        "wholesale_avg_cad": _json_number(evidence.wholesale_avg_cad),
        "wholesale_high_cad": _json_number(evidence.wholesale_high_cad),
        "trade_in_value_cad": _json_number(evidence.trade_in_value_cad),
        "retail_value_cad": _json_number(evidence.retail_value_cad),
        "auction_sale_low_cad": _json_number(evidence.auction_sale_low_cad),
        "auction_sale_avg_cad": _json_number(evidence.auction_sale_avg_cad),
        "auction_sale_high_cad": _json_number(evidence.auction_sale_high_cad),
        "bid_count": evidence.bid_count,
        "bidder_count": evidence.bidder_count,
        "high_bid_cad": _json_number(evidence.high_bid_cad),
        "sale_price_cad": _json_number(evidence.sale_price_cad),
        "reserve_price_cad": _json_number(evidence.reserve_price_cad),
        "condition_grade": evidence.condition_grade,
        "condition_score": _json_number(evidence.condition_score),
        "condition_notes": evidence.condition_notes,
        "buyer_fee_cad": _json_number(evidence.buyer_fee_cad),
        "transport_estimate_cad": _json_number(evidence.transport_estimate_cad),
        "reconditioning_estimate_cad": _json_number(evidence.reconditioning_estimate_cad),
        "notes": evidence.notes,
        "raw_payload": evidence.raw_payload or {},
        "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
        "updated_at": evidence.updated_at.isoformat() if evidence.updated_at else None,
    }


def wholesale_evidence_summary_payload(
    session: Session,
    evidence_items: list[OpportunityWholesaleEvidence],
    *,
    retail_max_buy_cad: object | None = None,
) -> dict:
    latest = evidence_items[0] if evidence_items else None
    support = wholesale_support_payload(latest, retail_max_buy_cad=retail_max_buy_cad)
    return {
        "status": _summary_status(latest, support),
        "count": len(evidence_items),
        "latest": _wholesale_payload_with_document(session, latest) if latest is not None else None,
        "support": support,
        "evidence": [_wholesale_payload_with_document(session, item) for item in evidence_items],
    }


def wholesale_support_payload(
    evidence: OpportunityWholesaleEvidence | None,
    *,
    retail_max_buy_cad: object | None = None,
) -> dict:
    if evidence is None:
        return {
            "status": "missing",
            "source": None,
            "support_low_cad": None,
            "support_target_cad": None,
            "support_high_cad": None,
            "condition_adjustment_pct": None,
            "supported_max_buy_cad": None,
            "suggested_opening_bid_cad": None,
            "retail_max_buy_cad": _json_number(retail_max_buy_cad),
            "retail_max_exceeds_support": False,
        }

    representative = _representative_value(evidence)
    if representative is None:
        return {
            "status": "needs_values",
            "source": evidence.provider or evidence.source_type,
            "support_low_cad": None,
            "support_target_cad": None,
            "support_high_cad": None,
            "condition_adjustment_pct": _condition_adjustment(evidence),
            "supported_max_buy_cad": None,
            "suggested_opening_bid_cad": None,
            "retail_max_buy_cad": _json_number(retail_max_buy_cad),
            "retail_max_exceeds_support": False,
        }

    low = _first_number(evidence.wholesale_low_cad, evidence.auction_sale_low_cad) or representative * 0.92
    high = _first_number(evidence.wholesale_high_cad, evidence.auction_sale_high_cad) or representative * 1.08
    adjustment = _condition_adjustment(evidence)
    target = representative * (1 + adjustment)
    deductions = sum(
        value
        for value in [
            _number(evidence.buyer_fee_cad),
            _number(evidence.transport_estimate_cad),
            _number(evidence.reconditioning_estimate_cad),
        ]
        if value is not None
    )
    supported_max_buy = max(target - deductions, 0)
    suggested_bid = supported_max_buy * 0.96
    retail_max = _number(retail_max_buy_cad)

    return {
        "status": "supported",
        "source": evidence.provider or evidence.source_type,
        "support_low_cad": round(low, 2),
        "support_target_cad": round(target, 2),
        "support_high_cad": round(high, 2),
        "condition_adjustment_pct": round(adjustment * 100, 2),
        "supported_max_buy_cad": round(supported_max_buy, 2),
        "suggested_opening_bid_cad": round(suggested_bid, 2),
        "retail_max_buy_cad": _json_number(retail_max_buy_cad),
        "retail_max_exceeds_support": bool(retail_max is not None and retail_max > supported_max_buy),
    }


def wholesale_risk_factors(
    evidence: OpportunityWholesaleEvidence | None,
    *,
    retail_max_buy_cad: object | None = None,
) -> list[str]:
    if evidence is None:
        return []

    support = wholesale_support_payload(evidence, retail_max_buy_cad=retail_max_buy_cad)
    factors = []
    if support["status"] == "needs_values":
        factors.append("wholesale evidence saved without valuation values")
    if support.get("retail_max_exceeds_support"):
        factors.append("retail-derived max buy exceeds wholesale support")
    if evidence.bid_count is not None and evidence.bid_count < 3:
        factors.append("low auction bid activity")
    if evidence.bidder_count is not None and evidence.bidder_count < 2:
        factors.append("low bidder count")
    if evidence.condition_grade in {"rough", "auction_1", "auction_2"}:
        factors.append("auction condition grade below average")
    sale_price = _number(evidence.sale_price_cad)
    supported_max = _number(support.get("supported_max_buy_cad"))
    if sale_price is not None and supported_max is not None and sale_price > supported_max:
        factors.append("auction sale price exceeds wholesale supported max buy")
    return factors


def _wholesale_payload_with_document(
    session: Session,
    evidence: OpportunityWholesaleEvidence | None,
) -> dict | None:
    if evidence is None:
        return None
    document = session.get(OpportunityDocument, evidence.document_id) if evidence.document_id else None
    return wholesale_evidence_payload(evidence, document)


def _summary_status(evidence: OpportunityWholesaleEvidence | None, support: dict) -> str:
    if evidence is None:
        return "missing"
    if support.get("status") == "supported":
        if support.get("retail_max_exceeds_support"):
            return "support_below_retail_max"
        return "supported"
    return "needs_values"


def _representative_value(evidence: OpportunityWholesaleEvidence) -> float | None:
    priority = [
        _number(evidence.wholesale_avg_cad),
        _number(evidence.trade_in_value_cad),
        _number(evidence.auction_sale_avg_cad),
        _number(evidence.high_bid_cad),
        _number(evidence.sale_price_cad),
    ]
    first = next((value for value in priority if value is not None), None)
    if first is not None:
        return first
    values = [
        _number(evidence.wholesale_low_cad),
        _number(evidence.wholesale_high_cad),
        _number(evidence.auction_sale_low_cad),
        _number(evidence.auction_sale_high_cad),
    ]
    filtered = [value for value in values if value is not None]
    return median(filtered) if filtered else None


def _condition_adjustment(evidence: OpportunityWholesaleEvidence) -> float:
    grade = evidence.condition_grade
    if grade in {"extra_clean", "auction_5"}:
        return 0.03
    if grade in {"clean", "auction_4"}:
        return 0.01
    if grade in {"rough", "auction_1", "auction_2"}:
        return -0.06
    return 0.0


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
        raise WholesaleEvidenceError("Linked document not found for this opportunity")
    return document


def _validate_source_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in WHOLESALE_SOURCE_TYPES:
        raise WholesaleEvidenceError(
            f"Unsupported wholesale source type. Allowed values: {', '.join(sorted(WHOLESALE_SOURCE_TYPES))}"
        )
    return normalized


def _validate_condition_grade(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in CONDITION_GRADES:
        raise WholesaleEvidenceError(
            f"Unsupported condition grade. Allowed values: {', '.join(sorted(CONDITION_GRADES))}"
        )
    return normalized


def _first_number(*values: object) -> float | None:
    for value in values:
        number = _number(value)
        if number is not None:
            return number
    return None


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _json_number(value: object):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
