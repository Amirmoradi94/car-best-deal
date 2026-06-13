from pathlib import Path

import pytest

from app.core.config import Settings
from app.scraping.adapters.autotrader import AutoTraderAdapter
from app.scraping.contracts import SearchFilters, SourceSnapshot


@pytest.mark.asyncio
async def test_autotrader_fixture_search_returns_refs() -> None:
    adapter = AutoTraderAdapter(Settings(SCRAPING_FIXTURE_MODE=True))

    refs = await adapter.search(SearchFilters(make="Honda", model="Civic", year_min=2020, limit=25))

    assert len(refs) == 2
    assert refs[0].source_name == "autotrader"
    assert refs[0].source_listing_id == "at-001"
    assert refs[0].price_cad == 18995


@pytest.mark.asyncio
async def test_autotrader_fixture_search_returns_parsed_listings() -> None:
    adapter = AutoTraderAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    snapshot = await adapter.fetch_search_snapshot(SearchFilters(make="Honda", model="Civic", year_min=2020, limit=25))

    listings = adapter.parse_search_listings(snapshot.html, limit=25)

    assert len(listings) == 2
    assert listings[0].title.value == "2020 Honda Civic EX"
    assert listings[0].asking_price_cad.value == 18995
    assert listings[0].year.value == 2020
    assert listings[0].make.value == "Honda"
    assert listings[0].model.value == "Civic"


@pytest.mark.asyncio
async def test_autotrader_fixture_listing_parses_fields_and_images() -> None:
    adapter = AutoTraderAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    html = Path("fixtures/html/autotrader/listing_detail.html").read_text()
    snapshot = SourceSnapshot(
        source_name="autotrader",
        url="https://www.autotrader.ca/a/honda/civic/montreal/quebec/at-001/",
        html=html,
    )

    parsed = await adapter.parse_listing(snapshot)

    assert parsed.title.value == "2020 Honda Civic EX"
    assert parsed.asking_price_cad.value == 18995
    assert parsed.mileage_km.value == 82000
    assert parsed.location_city.value == "Montreal"
    assert parsed.location_province.value == "QC"
    assert parsed.year.value == 2020
    assert parsed.make.value == "Honda"
    assert parsed.model.value == "Civic"
    assert parsed.trim.value == "EX"
    assert len(parsed.images) == 2


def test_autotrader_live_search_fixture_returns_refs_from_next_data() -> None:
    adapter = AutoTraderAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    html = Path("fixtures/html/autotrader/search_results_live.html").read_text()

    refs = adapter.parse_search_results(html, limit=50)

    assert len(refs) == 20
    assert refs[0].source_listing_id == "efaa3478-4e0a-496b-bd16-713a5be3d23a"
    assert refs[0].url.startswith("https://www.autotrader.ca/offers/honda-civic")
    assert refs[0].price_cad == 25998
    assert refs[0].location == "MONTRÉAL, QC"


def test_autotrader_live_search_fixture_returns_parsed_listings_from_next_data() -> None:
    adapter = AutoTraderAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    html = Path("fixtures/html/autotrader/search_results_live.html").read_text()

    listings = adapter.parse_search_listings(html, limit=50)

    assert len(listings) == 20
    assert listings[0].title.value == "2024 Honda Civic Sport AUTO A/C TOIT GR ELECT MAGS CAM BLUETOOTH"
    assert listings[0].asking_price_cad.value == 25998
    assert listings[0].mileage_km.value == 28028
    assert listings[0].location_city.value == "MONTRÉAL"
    assert listings[0].location_province.value == "QC"
    assert listings[0].year.value == 2024
    assert listings[0].make.value == "Honda"
    assert listings[0].model.value == "Civic"
    assert len(listings[0].images) == 10


def test_autotrader_live_listing_fixture_parses_detail_next_data() -> None:
    adapter = AutoTraderAdapter(Settings(SCRAPING_FIXTURE_MODE=True))
    html = Path("fixtures/html/autotrader/listing_detail_live.html").read_text()

    parsed = adapter.parse_listing_html(
        "https://www.autotrader.ca/offers/honda-civic-sport-auto-a-c-toit-gr-elect-mags-cam-bluetooth-gasoline-grey-cat_ma31gr200622va2411tr7208-efaa3478-4e0a-496b-bd16-713a5be3d23a",
        html,
    )

    assert parsed.title.value == "2024 Honda Civic Sport AUTO A/C TOIT GR ELECT MAGS CAM BLUETOOTH"
    assert parsed.asking_price_cad.value == 25998
    assert parsed.mileage_km.value == 28028
    assert parsed.location_city.value == "MONTRÉAL"
    assert parsed.location_province.value == "QC"
    assert parsed.year.value == 2024
    assert parsed.make.value == "Honda"
    assert parsed.model.value == "Civic"
    assert parsed.raw_fields["body_type"] == "Sedan"
    assert parsed.raw_fields["drivetrain"] == "Front Wheel Drive"
    assert len(parsed.images) == 10
