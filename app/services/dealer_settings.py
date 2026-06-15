from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DealerSettingsModel
from app.domain.enums import RiskTolerance
from app.domain.models import DealerSettings
from app.services.saved_searches import get_or_create_default_dealer


DEFAULT_PREFERRED_BRANDS = ["Honda", "Toyota"]
DEFAULT_PREFERRED_MODELS = ["Civic", "Corolla"]


def get_or_create_dealer_settings(session: Session) -> DealerSettingsModel:
    dealer = get_or_create_default_dealer(session)
    settings = session.scalar(
        select(DealerSettingsModel).where(DealerSettingsModel.dealer_account_id == dealer.id)
    )
    if settings is not None:
        return settings
    settings = DealerSettingsModel(
        dealer_account_id=dealer.id,
        default_target_profit_cad=2500,
        risk_tolerance=RiskTolerance.MEDIUM.value,
        preferred_brands=list(DEFAULT_PREFERRED_BRANDS),
        preferred_models=list(DEFAULT_PREFERRED_MODELS),
        default_search_radius_km=50,
        include_overpriced_default=False,
        candidate_score_threshold=75,
        max_candidate_count=50,
        max_images_per_candidate=10,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def update_dealer_settings(session: Session, updates: dict[str, Any]) -> DealerSettingsModel:
    settings = get_or_create_dealer_settings(session)
    for key, value in updates.items():
        if value is None:
            continue
        if key in {"preferred_brands", "preferred_models"}:
            setattr(settings, key, _normalized_terms(value))
        elif key == "risk_tolerance":
            setattr(settings, key, RiskTolerance(value).value)
        elif key == "target_profit_cad":
            settings.default_target_profit_cad = value
        else:
            setattr(settings, key, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def dealer_settings_payload(settings: DealerSettingsModel) -> dict[str, Any]:
    return {
        "id": settings.id,
        "dealer_account_id": settings.dealer_account_id,
        "target_profit_cad": _number(settings.default_target_profit_cad),
        "risk_tolerance": settings.risk_tolerance,
        "preferred_brands": list(settings.preferred_brands or []),
        "preferred_models": list(settings.preferred_models or []),
        "default_search_radius_km": settings.default_search_radius_km,
        "include_overpriced_default": settings.include_overpriced_default,
        "candidate_score_threshold": _number(settings.candidate_score_threshold),
        "max_candidate_count": settings.max_candidate_count,
        "max_images_per_candidate": settings.max_images_per_candidate,
        "created_at": settings.created_at.isoformat() if settings.created_at else None,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


def domain_dealer_settings(settings: DealerSettingsModel) -> DealerSettings:
    return DealerSettings(
        target_profit_cad=_number(settings.default_target_profit_cad),
        risk_tolerance=RiskTolerance(settings.risk_tolerance),
        preferred_brands=tuple(settings.preferred_brands or []),
        preferred_models=tuple(settings.preferred_models or []),
        candidate_score_threshold=_number(settings.candidate_score_threshold),
        max_candidate_count=settings.max_candidate_count,
        max_images_per_candidate=settings.max_images_per_candidate,
    )


def default_domain_dealer_settings() -> DealerSettings:
    return DealerSettings(
        target_profit_cad=2500,
        risk_tolerance=RiskTolerance.MEDIUM,
        preferred_brands=tuple(DEFAULT_PREFERRED_BRANDS),
        preferred_models=tuple(DEFAULT_PREFERRED_MODELS),
        candidate_score_threshold=75,
        max_candidate_count=50,
        max_images_per_candidate=10,
    )


def _normalized_terms(values: list[str]) -> list[str]:
    seen = set()
    terms = []
    for value in values:
        term = str(value).strip()
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def _number(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value)
