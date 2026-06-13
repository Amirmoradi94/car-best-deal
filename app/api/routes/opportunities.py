from pathlib import Path

from fastapi import APIRouter

from app.services.fixture_runner import score_fixture


router = APIRouter()


@router.get("")
def list_opportunities() -> list[dict]:
    scored = score_fixture(Path("fixtures/listings/civic_target.json"))
    return [
        {
            "id": scored.listing.id,
            "source": scored.listing.source_name,
            "asking_price_cad": scored.listing.asking_price_cad,
            "deal_score": scored.deal_score,
            "recommendation": scored.recommendation,
            "is_overpriced": scored.is_overpriced,
            "missing_key_data": scored.risk.missing_verifications,
        }
    ]


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: str) -> dict:
    scored = score_fixture(Path("fixtures/listings/civic_target.json"))
    return {
        "id": opportunity_id,
        "listing": scored.listing,
        "pricing": scored.pricing,
        "risk": scored.risk,
        "deal_score": scored.deal_score,
        "confidence_by_section": scored.confidence_by_section,
    }

