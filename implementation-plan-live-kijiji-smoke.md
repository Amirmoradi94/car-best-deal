# Implementation Plan: Live Kijiji Zyte Smoke

## Objective

Validate the live Kijiji scraping path through Zyte, save real HTML fixtures, and harden the Kijiji parser against the captured page structure.

## Scope

This step includes:

- Running the live Kijiji smoke CLI with `.env` configuration.
- Saving the live search HTML fixture.
- Fetching and saving the first listing fixture if a listing reference is parsed.
- Inspecting saved HTML for real selectors and embedded data.
- Updating the Kijiji adapter as needed.
- Adding tests for captured fixtures.

This step excludes:

- Production-grade full Kijiji coverage.
- AutoTrader adapter.
- Gemini fallback extraction.
- Scheduled crawling.
- Database persistence.

## Execution Steps

1. Run live CLI:

   ```bash
   uv run python -m app.cli.scrape_kijiji \
     "2020 Honda Civic Montreal" \
     --save-search-fixture fixtures/html/kijiji/search_results_live.html \
     --fetch-first-listing \
     --save-listing-fixture fixtures/html/kijiji/listing_detail_live.html
   ```

2. If listing refs are returned:

   - Confirm first listing fixture exists.
   - Add tests against `*_live.html`.
   - Verify parsed fields.

3. If no listing refs are returned:

   - Inspect live search HTML.
   - Identify whether Kijiji returned search results, a blocked page, or a consent/challenge page.
   - Update parser only if the page contains accessible listing data.
   - Keep source failure behavior if page is blocked or unavailable.

4. Run tests:

   ```bash
   uv run --extra dev pytest
   ```

## Done Criteria

- Live search fixture is saved.
- CLI result is understood.
- Parser is updated if real listing data is available.
- Tests pass.

