from app.domain.enums import SellerType
from app.domain.models import ListingSnapshot, VehicleProfile
from app.scraping.contracts import SearchFilters
from app.services.relevance import infer_search_intent, score_listing_relevance


def test_exact_make_model_year_match_scores_high() -> None:
    intent = infer_search_intent(SearchFilters(query="2020 Honda Civic Montreal"))
    listing = _listing("1", 2020, "Honda", "Civic", "EX")

    relevance = score_listing_relevance(listing, intent)

    assert relevance.keep is True
    assert relevance.score >= 0.85
    assert "make_match" in relevance.reasons
    assert "model_match" in relevance.reasons


def test_off_query_vehicle_is_filtered() -> None:
    intent = infer_search_intent(SearchFilters(query="2020 Honda Civic Montreal"))
    listing = _listing("2", 2025, "Volkswagen", "Tiguan", "Trendline")

    relevance = score_listing_relevance(listing, intent)

    assert relevance.keep is False
    assert relevance.score < 0.45
    assert "make_mismatch" in relevance.reasons
    assert "model_mismatch" in relevance.reasons


def test_structured_filters_define_intent_without_query() -> None:
    intent = infer_search_intent(SearchFilters(make="Toyota", model="Corolla", year_min=2021))
    listing = _listing("3", 2021, "Toyota", "Corolla", "LE")

    relevance = score_listing_relevance(listing, intent)

    assert relevance.keep is True
    assert relevance.score >= 0.85


def _listing(listing_id: str, year: int, make: str, model: str, trim: str) -> ListingSnapshot:
    return ListingSnapshot(
        id=listing_id,
        source_name="kijiji",
        url=f"https://example.test/{listing_id}",
        vehicle=VehicleProfile(year=year, make=make, model=model, trim=trim),
        asking_price_cad=15000,
        seller_type=SellerType.UNKNOWN,
    )
