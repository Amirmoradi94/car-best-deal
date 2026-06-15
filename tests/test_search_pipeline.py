from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.enums import SellerType
from app.scraping.errors import SourceFailureDetail, SourceFailureReason, SourceScrapingError
from app.scraping.contracts import FieldValue, ParsedListing, SearchFilters, SourceSnapshot
from app.services.ai_extraction import AIExtractionService
from app.services.image_risk import DeterministicImageRiskAnalyzer, GeminiImageRiskAnalyzer
from app.services.search_pipeline import SearchPipeline


@pytest.mark.asyncio
async def test_fixture_backed_search_returns_ranked_opportunities() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_fixture_backed_search(
        SearchFilters(make="Honda", model="Civic", year_min=2020, limit=25)
    )

    assert len(results) == 4
    assert results[0].deal_score >= results[1].deal_score
    assert results[0].pricing.retail_mid_cad > 0
    assert results[0].pricing.preliminary is True
    assert {result.listing.source_name for result in results} == {"kijiji", "autotrader"}


@pytest.mark.asyncio
async def test_kijiji_batch_search_uses_same_batch_comparables() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_kijiji_batch_search(
        SearchFilters(make="Honda", model="Civic", year_min=2020, limit=25)
    )

    assert len(results) == 2
    assert all(result.pricing.comparable_count == 1 for result in results)
    assert {result.listing.id for result in results} == {"kijiji-001", "kijiji-002"}


@pytest.mark.asyncio
async def test_kijiji_batch_search_applies_relevance_metadata() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_kijiji_batch_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25)
    )

    assert len(results) == 2
    assert all(result.relevance_score >= 0.85 for result in results)
    assert all("make_match" in result.relevance_reasons for result in results)


@pytest.mark.asyncio
async def test_multi_source_batch_search_combines_kijiji_and_autotrader() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_multi_source_batch_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25)
    )

    assert len(results) == 4
    assert {result.listing.source_name for result in results} == {"kijiji", "autotrader"}
    assert all(result.pricing.comparable_count >= 1 for result in results)
    assert all(result.listing.id.startswith(("kijiji:", "autotrader:")) for result in results)


@pytest.mark.asyncio
async def test_source_batch_search_can_limit_to_one_source() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_source_batch_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25),
        sources=("autotrader",),
    )

    assert len(results) == 2
    assert {result.listing.source_name for result in results} == {"autotrader"}
    assert all(not result.listing.id.startswith("autotrader:") for result in results)


@pytest.mark.asyncio
async def test_source_batch_search_returns_partial_results_when_one_source_fails() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    async def failing_fetch(_filters):
        raise SourceScrapingError(
            SourceFailureDetail(
                source_name="kijiji",
                reason=SourceFailureReason.SOURCE_UNAVAILABLE,
                url="https://www.kijiji.ca/down",
                message="Kijiji unavailable",
                retryable=True,
            )
        )

    pipeline.kijiji.fetch_search_snapshot = failing_fetch

    result = await pipeline.run_source_batch_search_with_statuses(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25),
        sources=("kijiji", "autotrader"),
    )

    assert result.scored_items
    assert {item.listing.source_name for item in result.scored_items} == {"autotrader"}
    statuses = {status.source_name: status for status in result.source_statuses}
    assert statuses["kijiji"].status == "failed"
    assert statuses["kijiji"].reason == "source_unavailable"
    assert statuses["kijiji"].retryable is True
    assert statuses["autotrader"].status == "ok"
    assert statuses["autotrader"].listing_count == 2


@pytest.mark.asyncio
async def test_source_batch_search_marks_empty_source_without_failing_run() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    def empty_parse(_html, limit=25):
        return []

    pipeline.kijiji.parse_search_listings = empty_parse

    result = await pipeline.run_source_batch_search_with_statuses(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25),
        sources=("kijiji",),
    )

    assert result.scored_items == []
    assert len(result.source_statuses) == 1
    assert result.source_statuses[0].status == "empty"
    assert result.source_statuses[0].reason == "no_results"


@pytest.mark.asyncio
async def test_source_batch_search_raises_when_all_selected_sources_fail() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    async def failing_fetch(_filters):
        raise RuntimeError("source timeout")

    pipeline.kijiji.fetch_search_snapshot = failing_fetch

    with pytest.raises(ValueError, match="All selected sources failed"):
        await pipeline.run_source_batch_search_with_statuses(
            SearchFilters(query="2020 Honda Civic Montreal", limit=25),
            sources=("kijiji",),
        )


@pytest.mark.asyncio
async def test_previsit_candidate_search_enriches_only_capped_candidates() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))
    fetch_count = 0
    original_fetch_listing = pipeline.kijiji.fetch_listing

    async def counted_fetch_listing(ref):
        nonlocal fetch_count
        fetch_count += 1
        return await original_fetch_listing(ref)

    pipeline.kijiji.fetch_listing = counted_fetch_listing

    results = await pipeline.run_previsit_candidate_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25),
        max_candidates=2,
    )

    assert len(results) == 2
    assert fetch_count == 2
    assert all(result.listing.has_image_risk for result in results)
    assert all(result.listing.image_risk_reasons == ("too_few_listing_images",) for result in results)
    assert all(len(result.listing.image_urls) == 3 for result in results)
    assert all("image_analysis_risk_adjustment" in result.risk.risk_factors for result in results)


@pytest.mark.asyncio
async def test_previsit_candidate_search_can_enrich_autotrader_candidates() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_previsit_candidate_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25),
        max_candidates=4,
    )

    autotrader_results = [result for result in results if result.listing.source_name == "autotrader"]
    assert autotrader_results
    assert all(result.listing.has_image_risk for result in autotrader_results)
    assert all(result.listing.image_urls for result in autotrader_results)


@pytest.mark.asyncio
async def test_single_listing_analysis_scores_kijiji_url_against_comparables() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_single_listing_analysis(
        "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
        SearchFilters(limit=25),
        sources=("kijiji", "autotrader"),
    )

    assert len(results) == 1
    scored = results[0]
    assert scored.listing.source_name == "kijiji"
    assert scored.listing.vehicle.make == "Honda"
    assert scored.listing.vehicle.model == "Civic"
    assert scored.listing.has_image_risk is True
    assert scored.pricing.comparable_count >= 1
    assert scored.relevance_reasons == ("single_listing_url",)


@pytest.mark.asyncio
async def test_single_listing_analysis_uses_ai_listing_fallback_for_low_confidence_parse(tmp_path) -> None:
    settings = Settings(SCRAPING_FIXTURE_MODE=True, OBJECT_STORE_ROOT=str(tmp_path / "objects"))
    pipeline = SearchPipeline(settings, ai_extractor=AIExtractionService(settings))

    async def low_confidence_parse(snapshot):
        return ParsedListing(
            source_name="kijiji",
            url=snapshot.url,
            title=FieldValue("2020 Honda Civic accident special", 0.45),
            year=FieldValue(2020, 0.6),
            make=FieldValue("Honda", 0.6),
            model=FieldValue("Civic", 0.6),
            description=FieldValue("Accident claim listed. Asking $12,450 CAD. Mileage 82,100 km.", 0.5),
            seller_type=SellerType.PRIVATE,
            extraction_confidence=0.45,
        )

    pipeline.kijiji.parse_listing = low_confidence_parse

    results = await pipeline.run_single_listing_analysis(
        "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
        SearchFilters(limit=25),
        sources=("kijiji", "autotrader"),
    )

    scored = results[0]
    assert scored.listing.asking_price_cad == 12450
    assert scored.listing.vehicle.mileage_km == 82100
    assert "accident_reported" in scored.listing.ai_risk_flags
    assert {output["feature"] for output in scored.listing.ai_outputs}.issuperset(
        {"listing_extraction_fallback", "risk_language_detection"}
    )
    assert "ai_risk_language:accident_reported" in scored.risk.risk_factors


@pytest.mark.asyncio
async def test_single_listing_analysis_scores_autotrader_url_against_comparables() -> None:
    pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))

    results = await pipeline.run_single_listing_analysis(
        "https://www.autotrader.ca/a/honda/civic/montreal/quebec/at-001/",
        SearchFilters(limit=25),
        sources=("autotrader",),
        vin="2HGFC2F59LH000001",
    )

    assert len(results) == 1
    scored = results[0]
    assert scored.listing.source_name == "autotrader"
    assert scored.listing.vehicle.vin == "2HGFC2F59LH000001"
    assert scored.listing.image_urls
    assert scored.pricing.comparable_count >= 1


def test_pipeline_selects_gemini_image_analyzer_only_for_configured_live_mode() -> None:
    fixture_pipeline = SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True))
    live_pipeline = SearchPipeline(
        Settings(
            APP_MODE="live",
            SCRAPING_FIXTURE_MODE=False,
            GEMINI_IMAGE_ANALYSIS_ENABLED=True,
            GEMINI_API_KEY="test-key",
        )
    )

    assert isinstance(fixture_pipeline.image_risk_analyzer, DeterministicImageRiskAnalyzer)
    assert isinstance(live_pipeline.image_risk_analyzer, GeminiImageRiskAnalyzer)


@pytest.mark.asyncio
async def test_live_fixture_kijiji_batch_filters_off_query_results() -> None:
    settings = Settings(SCRAPING_FIXTURE_MODE=True)
    pipeline = SearchPipeline(settings)
    html = Path("fixtures/html/kijiji/search_results_live.html").read_text()

    async def fetch_live_snapshot(_filters):
        return SourceSnapshot(
            source_name="kijiji",
            url="https://www.kijiji.ca/b-cars-trucks/montreal/c174l1700281",
            html=html,
        )

    pipeline.kijiji.fetch_search_snapshot = fetch_live_snapshot

    results = await pipeline.run_kijiji_batch_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=10)
    )

    assert results
    assert all(result.relevance_score >= 0.45 for result in results)
    assert all(result.listing.vehicle.make.casefold() == "honda" for result in results)
