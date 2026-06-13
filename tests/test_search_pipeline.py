from pathlib import Path

import pytest

from app.core.config import Settings
from app.scraping.contracts import SearchFilters, SourceSnapshot
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
