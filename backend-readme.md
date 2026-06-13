# Backend Quick Start

## Install and Test

Use `uv` from the project root:

```bash
uv run --extra dev pytest
```

## Run API

```bash
uv run uvicorn app.api.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```

## Current Implementation

This includes the Milestone 1 backend slice:

- Domain enums and dataclasses.
- Fixture-backed scoring and pricing.
- Weighted comparable valuation.
- Preliminary max-buy-price calculation.
- Missing VIN/history/lien penalties.
- Overpriced classification.
- FastAPI route skeleton.
- SQLAlchemy model definitions.

Milestone 2 has also started:

- Environment-based scraping config.
- Zyte API client.
- Scraping contracts.
- Kijiji adapter skeleton.
- Kijiji-like HTML fixtures.
- Fixture-backed parser tests.
- Search pipeline that converts parsed listings into scored opportunities.
- Kijiji same-batch ranking using parsed search-result listings as comparables.
- Query relevance filtering so off-query Kijiji results do not rank as first-class opportunities.

The app defaults to fixture scraping mode. To prepare for live Zyte-backed fetching, copy `.env.example` to `.env`, set `ZYTE_API_KEY`, and set:

```text
SCRAPING_FIXTURE_MODE=false
SCRAPING_USE_ZYTE=true
```

Live AutoTrader coverage, production-grade Kijiji selectors, Gemini calls, Alembic migrations, and real PostgreSQL wiring are intentionally not implemented yet.

## Kijiji Batch Ranking

The search pipeline can rank parsed Kijiji search results directly:

```bash
uv run python - <<'PY'
from app.services.search_pipeline import SearchPipeline
from app.scraping.contracts import SearchFilters
import asyncio

async def main():
    results = await SearchPipeline().run_kijiji_batch_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=5)
    )
    for item in results:
        print(item.listing.id, item.listing.vehicle.year, item.listing.vehicle.make, item.listing.vehicle.model, item.deal_score)

asyncio.run(main())
PY
```

In fixture mode, this uses saved HTML fixtures. In live mode, it fetches Kijiji through Zyte, parses JSON-LD listing data, builds same-batch comparables, and returns ranked opportunities.

The pipeline now filters parsed search results by relevance to the requested year/make/model/query. For example, a search for `2020 Honda Civic Montreal` will filter unrelated Kia/Mazda/Volkswagen results before ranking. Borderline matches can be kept with a deal-score penalty; clearly off-query listings are removed from the scored opportunity list.

## Kijiji Scraping Smoke Command

Run safely against local fixtures:

```bash
uv run python -m app.cli.scrape_kijiji "2020 Honda Civic Montreal" --fixture-mode
```

Run live through Zyte after configuring `.env`:

```bash
uv run python -m app.cli.scrape_kijiji "2020 Honda Civic Montreal"
```

Fetch the first listing from the search results as well:

```bash
uv run python -m app.cli.scrape_kijiji "2020 Honda Civic Montreal" --fetch-first-listing
```

Save live HTML into parser fixtures:

```bash
uv run python -m app.cli.scrape_kijiji \
  "2020 Honda Civic Montreal" \
  --save-search-fixture fixtures/html/kijiji/search_results_live.html \
  --fetch-first-listing \
  --save-listing-fixture fixtures/html/kijiji/listing_detail_live.html
```

The command saves raw snapshots through the local object store. By default, object data is written under `var/object-store`, which is ignored by git.
