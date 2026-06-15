from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings as get_app_settings
from app.db.session import get_session
from app.services.dealer_settings import (
    dealer_settings_payload,
    get_or_create_dealer_settings,
    update_dealer_settings,
)


router = APIRouter()


class SettingsResponse(BaseModel):
    id: str
    dealer_account_id: str
    target_profit_cad: float
    risk_tolerance: Literal["low", "medium", "high"]
    preferred_brands: list[str]
    preferred_models: list[str]
    default_search_radius_km: int
    include_overpriced_default: bool
    candidate_score_threshold: float
    max_candidate_count: int
    max_images_per_candidate: int
    created_at: str | None = None
    updated_at: str | None = None


class SettingsUpdateRequest(BaseModel):
    target_profit_cad: float | None = Field(default=None, ge=0, le=100_000)
    risk_tolerance: Literal["low", "medium", "high"] | None = None
    preferred_brands: list[str] | None = Field(default=None, max_length=25)
    preferred_models: list[str] | None = Field(default=None, max_length=50)
    default_search_radius_km: int | None = Field(default=None, ge=1, le=1000)
    include_overpriced_default: bool | None = None
    candidate_score_threshold: float | None = Field(default=None, ge=0, le=100)
    max_candidate_count: int | None = Field(default=None, ge=1, le=50)
    max_images_per_candidate: int | None = Field(default=None, ge=0, le=25)

    @field_validator("preferred_brands", "preferred_models")
    @classmethod
    def validate_terms(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return [value.strip() for value in values if value.strip()]


@router.get("", response_model=SettingsResponse)
def get_settings(session: Session = Depends(get_session)) -> dict:
    return dealer_settings_payload(get_or_create_dealer_settings(session))


@router.patch("", response_model=SettingsResponse)
def patch_settings(
    payload: SettingsUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    settings = update_dealer_settings(
        session,
        payload.model_dump(exclude_unset=True),
    )
    return dealer_settings_payload(settings)


@router.get("/source-health")
def get_source_health(settings: Settings = Depends(get_app_settings)) -> dict:
    broad_live_enabled = settings.app_mode == "live" and not settings.scraping_fixture_mode
    live_url_intake_enabled = (
        settings.app_mode in {"pilot", "live"}
        and not settings.scraping_fixture_mode
        and bool(settings.zyte_api_key)
    )
    return {
        "app_mode": settings.app_mode,
        "fixture_mode": settings.scraping_fixture_mode,
        "zyte_configured": bool(settings.zyte_api_key),
        "broad_live_discovery_enabled": broad_live_enabled,
        "live_url_intake_enabled": live_url_intake_enabled,
        "policy": (
            "pilot_url_only"
            if settings.app_mode == "pilot"
            else "fixture_only"
            if settings.app_mode == "fixture"
            else "live_enabled"
        ),
        "sources": [
            {
                "source_name": "kijiji",
                "detail_url_intake": live_url_intake_enabled or settings.app_mode == "fixture",
                "broad_discovery": broad_live_enabled or settings.app_mode == "fixture",
            },
            {
                "source_name": "autotrader",
                "detail_url_intake": live_url_intake_enabled or settings.app_mode == "fixture",
                "broad_discovery": broad_live_enabled or settings.app_mode == "fixture",
            },
        ],
    }
