from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


class SettingsResponse(BaseModel):
    target_profit_cad: float = 2500
    risk_tolerance: str = "medium"
    preferred_brands: list[str] = ["Honda", "Toyota"]
    preferred_models: list[str] = ["Civic", "Corolla"]
    candidate_score_threshold: float = 75
    max_candidate_count: int = 50
    max_images_per_candidate: int = 10


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return SettingsResponse()

