from pathlib import Path

import pytest

from app.core.config import Settings
from app.scraping.adapters.kijiji import KijijiAdapter
from app.scraping.contracts import SearchFilters, SourceSnapshot


@pytest.mark.asyncio
async def test_kijiji_fixture_search_returns_refs() -> None:
    adapter = KijijiAdapter(Settings(SCRAPING_FIXTURE_MODE=True))

    refs = await adapter.search(SearchFilters(make="Honda", model="Civic", year_min=2020, limit=25))

    assert len(refs) == 2
    assert refs[0].source_name == "kijiji"
    assert refs[0].source_listing_id == "kijiji-001"
    assert refs[0].price_cad == 13000


@pytest.mark.asyncio
async def test_kijiji_fixture_search_returns_parsed_listings() -> None:
    adapter = KijijiAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    snapshot = await adapter.fetch_search_snapshot(SearchFilters(make="Honda", model="Civic", year_min=2020, limit=25))

    listings = adapter.parse_search_listings(snapshot.html, limit=25)

    assert len(listings) == 2
    assert listings[0].title.value == "2020 Honda Civic EX"
    assert listings[0].asking_price_cad.value == 13000
    assert listings[0].year.value == 2020
    assert listings[0].make.value == "Honda"
    assert listings[0].model.value == "Civic"


@pytest.mark.asyncio
async def test_kijiji_fixture_search_snapshot_exposes_raw_html() -> None:
    adapter = KijijiAdapter(Settings(SCRAPING_FIXTURE_MODE=True))

    snapshot = await adapter.fetch_search_snapshot(SearchFilters(query="2020 Honda Civic Montreal"))

    assert snapshot.source_name == "kijiji"
    assert "2020 Honda Civic EX" in snapshot.html
    assert "q=2020+Honda+Civic+Montreal" in snapshot.url


@pytest.mark.asyncio
async def test_kijiji_fixture_listing_parses_fields_and_images() -> None:
    adapter = KijijiAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    html = Path("fixtures/html/kijiji/listing_detail.html").read_text()
    snapshot = SourceSnapshot(
        source_name="kijiji",
        url="https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
        html=html,
    )

    parsed = await adapter.parse_listing(snapshot)

    assert parsed.title.value == "2020 Honda Civic EX"
    assert parsed.asking_price_cad.value == 13000
    assert parsed.mileage_km.value == 85000
    assert parsed.location_city.value == "Montreal"
    assert parsed.location_province.value == "QC"
    assert parsed.year.value == 2020
    assert parsed.make.value == "Honda"
    assert parsed.model.value == "Civic"
    assert parsed.trim.value == "EX"
    assert len(parsed.images) == 3
    assert parsed.extraction_confidence >= 0.9


def test_kijiji_live_search_fixture_parses_json_ld_refs() -> None:
    path = Path("fixtures/html/kijiji/search_results_live.html")
    if not path.exists():
        return
    adapter = KijijiAdapter(Settings(SCRAPING_FIXTURE_MODE=True))

    refs = adapter.parse_search_results(path.read_text(), limit=10)

    assert len(refs) >= 1
    assert refs[0].url.startswith("https://www.kijiji.ca/v-cars-trucks/")
    assert refs[0].title
    assert refs[0].price_cad is not None


def test_kijiji_live_search_fixture_parses_json_ld_listings() -> None:
    path = Path("fixtures/html/kijiji/search_results_live.html")
    if not path.exists():
        return
    adapter = KijijiAdapter(Settings(SCRAPING_FIXTURE_MODE=True))

    listings = adapter.parse_search_listings(path.read_text(), limit=10)

    assert len(listings) >= 1
    assert listings[0].url.startswith("https://www.kijiji.ca/v-cars-trucks/")
    assert listings[0].title.value
    assert listings[0].asking_price_cad.value is not None
    assert listings[0].year.value is not None
    assert listings[0].make.value
    assert listings[0].model.value


def test_kijiji_live_listing_fixture_parses_json_ld_detail() -> None:
    path = Path("fixtures/html/kijiji/listing_detail_live.html")
    if not path.exists():
        return
    adapter = KijijiAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    url = "https://www.kijiji.ca/v-cars-trucks/ville-de-montreal/2015-kia-rio-econo-garantie-1-ans/1736738634"

    parsed = adapter.parse_listing_html(url, path.read_text())

    assert parsed.title.value
    assert parsed.asking_price_cad.value is not None
    assert parsed.mileage_km.value is not None
    assert parsed.year.value is not None
    assert parsed.make.value
    assert parsed.model.value
    assert parsed.images
