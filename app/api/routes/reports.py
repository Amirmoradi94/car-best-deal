from pathlib import Path

from fastapi import APIRouter

from app.services.fixture_runner import score_fixture


router = APIRouter()


@router.get("/{report_id}")
def get_report(report_id: str) -> dict:
    scored = score_fixture(Path("fixtures/listings/civic_target.json"))
    return {
        "id": report_id,
        "status": "preliminary" if scored.pricing.preliminary else "full",
        "recommendation": scored.recommendation,
        "retail_low_cad": scored.pricing.retail_low_cad,
        "retail_mid_cad": scored.pricing.retail_mid_cad,
        "retail_high_cad": scored.pricing.retail_high_cad,
        "max_buy_price_cad": scored.pricing.max_buy_price_cad,
        "starting_offer_cad": scored.pricing.starting_offer_cad,
        "confidence_by_section": scored.confidence_by_section,
        "missing_data": scored.risk.missing_verifications,
    }

