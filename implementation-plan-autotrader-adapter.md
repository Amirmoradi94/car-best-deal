# Implementation Plan: AutoTrader Adapter

## Objective

Add AutoTrader as the second marketplace source and combine it with Kijiji in the discovery-ranking pipeline.

## Scope

This milestone includes:

- AutoTrader source adapter.
- AutoTrader smoke CLI.
- Synthetic AutoTrader fixtures.
- Live AutoTrader fixture capture through Zyte.
- Parser tests for refs, parsed listings, and detail pages.
- Combined Kijiji + AutoTrader ranking pipeline.
- API output backed by combined source ranking.

This milestone excludes:

- Full province-wide search coverage.
- Authenticated dealer tools.
- Gemini fallback extraction.
- Database persistence.
- Advanced deduplication beyond basic URL/listing ID handling.

## Execution Steps

1. Implement `AutoTraderAdapter` with the same contract as Kijiji. Complete.
2. Add synthetic search/detail fixtures. Complete.
3. Add `scrape_autotrader` CLI. Complete.
4. Run live Zyte smoke and save. Complete:
   - `fixtures/html/autotrader/search_results_live.html`
   - `fixtures/html/autotrader/listing_detail_live.html`
5. Inspect the live fixture and harden parser. Complete:
   - Search pages expose listings through `__NEXT_DATA__.props.pageProps.listings`.
   - Detail pages expose the selected vehicle through `__NEXT_DATA__.props.pageProps.listingDetails`.
   - Parser now extracts URL, source listing ID, title, price, mileage, location, year/make/model/trim, seller fields, body style, drivetrain, and up to 10 images.
6. Extend `SearchPipeline` to run both Kijiji and AutoTrader. Complete.
7. Build comparables across the combined source batch. Complete.
8. Add tests and run verification. Complete.

## Done Criteria

- AutoTrader live smoke can save a search fixture.
- AutoTrader parser extracts refs/listings from saved fixtures.
- Combined search pipeline returns ranked opportunities from both sources.
- Tests pass.

## Verification

Run:

```bash
uv run --extra dev pytest
```

Live smoke used:

```bash
uv run python -m app.cli.scrape_autotrader \
  "2020 Honda Civic Montreal" \
  --limit 20 \
  --save-search-fixture fixtures/html/autotrader/search_results_live.html \
  --fetch-first-listing \
  --save-listing-fixture fixtures/html/autotrader/listing_detail_live.html
```
