from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LienProfile, OpportunityTitleEvidence


CLEAR_TITLE_STATUSES = {"clear", "released"}
BLOCKED_TITLE_STATUSES = {"lien_found", "payout_pending", "payout_ready", "payout_paid", "blocked"}


def create_lien_profile_from_title_evidence(
    session: Session,
    evidence: OpportunityTitleEvidence,
) -> LienProfile:
    existing = session.scalar(
        select(LienProfile).where(LienProfile.title_evidence_id == evidence.id)
    )
    if existing is not None:
        return existing

    profile = LienProfile(
        opportunity_id=evidence.opportunity_id,
        title_evidence_id=evidence.id,
        source_type=evidence.source_type,
        lien_status=_lien_status(evidence),
        title_status=evidence.title_clearance_status,
        evidence_summary=_evidence_summary(evidence),
        verified=evidence.title_clearance_status in CLEAR_TITLE_STATUSES,
        confidence=_confidence(evidence),
        lienholder_name=evidence.lienholder_name,
        lien_amount_cad=evidence.lien_amount_cad,
        payout_required=evidence.payout_required,
        payout_amount_cad=evidence.payout_amount_cad,
        payout_status=evidence.payout_status,
        raw_payload={
            "provider": evidence.provider,
            "lookup_reference": evidence.lookup_reference,
            "checked_at": evidence.checked_at,
            "document_id": evidence.document_id,
            "ownership_verified": evidence.ownership_verified,
            "seller_name": evidence.seller_name,
            "registered_owner_name": evidence.registered_owner_name,
            "notes": evidence.notes,
            "title_evidence_raw_payload": evidence.raw_payload or {},
        },
    )
    session.add(profile)
    session.flush()
    return profile


def latest_lien_profile(session: Session, opportunity_id: str) -> LienProfile | None:
    return session.scalar(
        select(LienProfile)
        .where(LienProfile.opportunity_id == opportunity_id)
        .order_by(LienProfile.created_at.desc(), LienProfile.id.desc())
    )


def list_lien_profiles(session: Session, opportunity_id: str) -> list[LienProfile]:
    return list(
        session.scalars(
            select(LienProfile)
            .where(LienProfile.opportunity_id == opportunity_id)
            .order_by(LienProfile.created_at.desc(), LienProfile.id.desc())
        )
    )


def lien_profile_payload(profile: LienProfile) -> dict:
    return {
        "id": profile.id,
        "opportunity_id": profile.opportunity_id,
        "title_evidence_id": profile.title_evidence_id,
        "source_type": profile.source_type,
        "lien_status": profile.lien_status,
        "title_status": profile.title_status,
        "evidence_summary": profile.evidence_summary,
        "verified": profile.verified,
        "confidence": _json_number(profile.confidence),
        "lienholder_name": profile.lienholder_name,
        "lien_amount_cad": _json_number(profile.lien_amount_cad),
        "payout_required": profile.payout_required,
        "payout_amount_cad": _json_number(profile.payout_amount_cad),
        "payout_status": profile.payout_status,
        "raw_payload": profile.raw_payload or {},
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def lien_profile_summary_payload(profiles: list[LienProfile]) -> dict:
    latest = profiles[0] if profiles else None
    return {
        "status": latest.lien_status if latest is not None else "missing",
        "count": len(profiles),
        "latest": lien_profile_payload(latest) if latest is not None else None,
        "profiles": [lien_profile_payload(profile) for profile in profiles],
    }


def _lien_status(evidence: OpportunityTitleEvidence) -> str:
    if evidence.title_clearance_status in CLEAR_TITLE_STATUSES:
        return "clear"
    if evidence.title_clearance_status in BLOCKED_TITLE_STATUSES:
        return evidence.title_clearance_status
    if evidence.lienholder_name or evidence.lien_amount_cad:
        return "lien_found"
    return "not_verified" if evidence.title_clearance_status == "unknown" else evidence.title_clearance_status


def _confidence(evidence: OpportunityTitleEvidence) -> float:
    if evidence.title_clearance_status in CLEAR_TITLE_STATUSES:
        return 0.9 if evidence.lookup_reference or evidence.document_id else 0.75
    if evidence.title_clearance_status in BLOCKED_TITLE_STATUSES:
        return 0.8 if evidence.lookup_reference or evidence.document_id else 0.65
    if evidence.title_clearance_status == "needs_review":
        return 0.45
    return 0.0


def _evidence_summary(evidence: OpportunityTitleEvidence) -> str:
    parts = [
        evidence.provider or evidence.source_type,
        evidence.lookup_reference,
        evidence.title_clearance_status.replace("_", " "),
    ]
    if evidence.lienholder_name:
        parts.append(f"lienholder {evidence.lienholder_name}")
    if evidence.payout_required:
        parts.append(f"payout {evidence.payout_status.replace('_', ' ')}")
    return " / ".join(part for part in parts if part)


def _json_number(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    return value

