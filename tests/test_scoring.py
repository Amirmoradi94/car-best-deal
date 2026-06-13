from pathlib import Path

from app.domain.enums import Recommendation
from app.services.fixture_runner import score_fixture


def test_fixture_scores_preliminary_opportunity() -> None:
    scored = score_fixture(Path("fixtures/listings/civic_target.json"))

    assert scored.pricing.preliminary is True
    assert "vin" in scored.risk.missing_verifications
    assert "vehicle_history" in scored.risk.missing_verifications
    assert "lien_verification" in scored.risk.missing_verifications
    assert scored.pricing.retail_mid_cad > scored.listing.asking_price_cad
    assert scored.deal_score > 0


def test_fixture_marks_good_discount_as_not_overpriced() -> None:
    scored = score_fixture(Path("fixtures/listings/civic_target.json"))

    assert scored.is_overpriced is False
    assert scored.recommendation in {
        Recommendation.BUY,
        Recommendation.BUY_ONLY_CHEAP,
        Recommendation.NEEDS_MORE_DATA,
    }


def test_overpriced_fixture_is_identified() -> None:
    scored = score_fixture(Path("fixtures/listings/civic_overpriced.json"))

    assert scored.is_overpriced is True
    assert scored.recommendation == Recommendation.BUY_ONLY_CHEAP
