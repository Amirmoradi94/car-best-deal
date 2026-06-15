from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateAnalysis, CandidateSnapshot, ImageAnalysis, Opportunity


@dataclass(frozen=True)
class StoredCandidateAnalysis:
    candidate_analysis: CandidateAnalysis
    image_analysis: ImageAnalysis


def create_candidate_analysis_from_snapshot(
    session: Session,
    *,
    opportunity: Opportunity,
    candidate: CandidateSnapshot,
    selected_reason: str = "promoted_candidate",
) -> StoredCandidateAnalysis:
    existing = session.scalar(
        select(CandidateAnalysis).where(
            CandidateAnalysis.opportunity_id == opportunity.id,
            CandidateAnalysis.candidate_snapshot_id == candidate.id,
        )
    )
    if existing is not None:
        image = _get_or_create_image_analysis(session, opportunity=opportunity, candidate=candidate, analysis=existing)
        return StoredCandidateAnalysis(candidate_analysis=existing, image_analysis=image)

    now = datetime.now(UTC)
    image_count = len(candidate.image_urls or [])
    analyzed_count = image_count if candidate.image_risk_reasons else 0
    analysis = CandidateAnalysis(
        opportunity_id=opportunity.id,
        candidate_snapshot_id=candidate.id,
        status="completed",
        selected_reason=selected_reason,
        score_at_selection=candidate.deal_score,
        max_images_to_analyze=image_count,
        images_discovered_count=image_count,
        images_analyzed_count=analyzed_count,
        started_at=now,
        completed_at=now,
        error_summary=None,
        analysis_summary={
            "recommendation": candidate.recommendation,
            "is_overpriced": candidate.is_overpriced,
            "missing_verifications": list((candidate.risk_summary or {}).get("missing_verifications", [])),
            "risk_factors": list((candidate.risk_summary or {}).get("risk_factors", [])),
            "pricing": dict(candidate.pricing_summary or {}),
        },
    )
    session.add(analysis)
    session.flush()
    image = _get_or_create_image_analysis(session, opportunity=opportunity, candidate=candidate, analysis=analysis)
    return StoredCandidateAnalysis(candidate_analysis=analysis, image_analysis=image)


def latest_candidate_analysis(session: Session, opportunity_id: str) -> CandidateAnalysis | None:
    return session.scalar(
        select(CandidateAnalysis)
        .where(CandidateAnalysis.opportunity_id == opportunity_id)
        .order_by(CandidateAnalysis.created_at.desc(), CandidateAnalysis.id.desc())
    )


def latest_image_analysis(session: Session, opportunity_id: str) -> ImageAnalysis | None:
    return session.scalar(
        select(ImageAnalysis)
        .where(ImageAnalysis.opportunity_id == opportunity_id)
        .order_by(ImageAnalysis.created_at.desc(), ImageAnalysis.id.desc())
    )


def candidate_analysis_summary_payload(analysis: CandidateAnalysis | None) -> dict:
    if analysis is None:
        return {"status": "missing", "latest": None}
    return {
        "status": analysis.status,
        "latest": candidate_analysis_payload(analysis),
    }


def image_analysis_summary_payload(analysis: ImageAnalysis | None) -> dict:
    if analysis is None:
        return {"status": "missing", "latest": None}
    return {
        "status": "completed",
        "latest": image_analysis_payload(analysis),
    }


def candidate_analysis_payload(analysis: CandidateAnalysis) -> dict:
    return {
        "id": analysis.id,
        "opportunity_id": analysis.opportunity_id,
        "candidate_snapshot_id": analysis.candidate_snapshot_id,
        "status": analysis.status,
        "selected_reason": analysis.selected_reason,
        "score_at_selection": _json_number(analysis.score_at_selection),
        "max_images_to_analyze": analysis.max_images_to_analyze,
        "images_discovered_count": analysis.images_discovered_count,
        "images_analyzed_count": analysis.images_analyzed_count,
        "started_at": analysis.started_at.isoformat() if analysis.started_at else None,
        "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
        "error_summary": analysis.error_summary,
        "analysis_summary": analysis.analysis_summary or {},
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "updated_at": analysis.updated_at.isoformat() if analysis.updated_at else None,
    }


def image_analysis_payload(analysis: ImageAnalysis) -> dict:
    return {
        "id": analysis.id,
        "opportunity_id": analysis.opportunity_id,
        "candidate_analysis_id": analysis.candidate_analysis_id,
        "candidate_snapshot_id": analysis.candidate_snapshot_id,
        "model_provider": analysis.model_provider,
        "model_name": analysis.model_name,
        "prompt_version": analysis.prompt_version,
        "image_urls": analysis.image_urls or [],
        "findings": analysis.findings or [],
        "visible_damage": analysis.visible_damage,
        "rust_detected": analysis.rust_detected,
        "panel_mismatch_detected": analysis.panel_mismatch_detected,
        "tire_wear_concern": analysis.tire_wear_concern,
        "interior_condition": analysis.interior_condition,
        "warning_lights_visible": analysis.warning_lights_visible,
        "odometer_visible": analysis.odometer_visible,
        "odometer_km": analysis.odometer_km,
        "vin_visible": analysis.vin_visible,
        "vin": analysis.vin,
        "risk_adjustment": _json_number(analysis.risk_adjustment),
        "confidence": _json_number(analysis.confidence),
        "raw_payload": analysis.raw_payload or {},
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "updated_at": analysis.updated_at.isoformat() if analysis.updated_at else None,
    }


def _get_or_create_image_analysis(
    session: Session,
    *,
    opportunity: Opportunity,
    candidate: CandidateSnapshot,
    analysis: CandidateAnalysis,
) -> ImageAnalysis:
    existing = session.scalar(
        select(ImageAnalysis).where(
            ImageAnalysis.opportunity_id == opportunity.id,
            ImageAnalysis.candidate_analysis_id == analysis.id,
        )
    )
    if existing is not None:
        return existing

    findings = list(candidate.image_risk_reasons or [])
    image = ImageAnalysis(
        opportunity_id=opportunity.id,
        candidate_analysis_id=analysis.id,
        candidate_snapshot_id=candidate.id,
        model_provider=_image_model_provider(candidate),
        model_name=_image_model_name(candidate),
        prompt_version="image-risk-v1",
        image_urls=list(candidate.image_urls or []),
        findings=findings,
        visible_damage=_flag(findings, {"visible_damage", "body_damage", "collision_damage"}),
        rust_detected=_flag(findings, {"rust", "corrosion"}),
        panel_mismatch_detected=_flag(findings, {"panel_mismatch", "mismatched_panels"}),
        tire_wear_concern=_flag(findings, {"tire_wear", "worn_tires"}),
        interior_condition=None,
        warning_lights_visible=_flag(findings, {"warning_lights", "dash_warning"}),
        odometer_visible=None,
        odometer_km=candidate.mileage_km,
        vin_visible=bool(candidate.vin),
        vin=candidate.vin,
        risk_adjustment=candidate.image_risk_adjustment,
        confidence=_image_confidence(candidate),
        raw_payload={
            "image_risk_reasons": findings,
            "image_count": len(candidate.image_urls or []),
            "confidence_by_section": dict(candidate.confidence_by_section or {}),
        },
    )
    session.add(image)
    session.flush()
    return image


def _image_model_provider(candidate: CandidateSnapshot) -> str:
    outputs = candidate.ai_outputs or []
    if any((output or {}).get("feature") == "image_risk" for output in outputs):
        return "ai"
    return "local"


def _image_model_name(candidate: CandidateSnapshot) -> str:
    outputs = candidate.ai_outputs or []
    for output in outputs:
        if (output or {}).get("feature") == "image_risk":
            return str(output.get("model") or "image-risk")
    return "deterministic-image-risk"


def _image_confidence(candidate: CandidateSnapshot) -> float:
    confidence = (candidate.confidence_by_section or {}).get("images")
    if confidence == "high":
        return 0.85
    if confidence == "medium":
        return 0.5
    if confidence == "low":
        return 0.25
    return 0.0


def _flag(findings: list[str], keywords: set[str]) -> bool | None:
    normalized = {str(finding).lower() for finding in findings}
    if not normalized:
        return None
    return bool(normalized.intersection(keywords))


def _json_number(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    return value

