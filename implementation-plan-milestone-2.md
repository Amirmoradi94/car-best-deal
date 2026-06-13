# Implementation Plan: Milestone 2

## Objective

Build the first search and scraping prototype for the Quebec used-car opportunity finder.

This milestone connects the existing fixture-backed scoring/pricing layer to a scraping architecture that can support AutoTrader and Kijiji. It starts with a Kijiji adapter skeleton and fixture-backed parser tests so source extraction can be developed safely before relying on live pages.

## Scope

Milestone 2 includes:

- Runtime configuration for external services.
- Zyte API client.
- Scraping contracts.
- Source adapter interface.
- Parser result types with field-level confidence.
- Kijiji search/listing adapter skeleton.
- HTML fixture parsing tests.
- Fixture-backed adapter mode for local development.
- API path that can run a search against fixture-backed parsed listings.

Milestone 2 excludes:

- Production-grade Kijiji and AutoTrader coverage.
- Authenticated source access.
- Paid data purchases.
- Gemini extraction fallback.
- Browser screenshot analysis.
- Full persistence of scraped snapshots.
- Live scheduled search worker.

## Build Sequence

### Step 1: Config

Add config for:

- `ZYTE_API_KEY`
- `ZYTE_API_URL`
- `SCRAPING_USE_ZYTE`
- `SCRAPING_FIXTURE_MODE`
- `SCRAPING_COUNTRY`
- `GEMINI_MODEL`

Use environment variables and safe defaults.

### Step 2: Scraping Contracts

Create domain objects:

- `SearchFilters`
- `SourceListingRef`
- `SourceSnapshot`
- `ParsedListing`
- `ParsedImage`
- `FieldValue`

Every extracted field should carry:

- Value.
- Confidence.
- Evidence.
- Extraction method.

### Step 3: Zyte Client

Implement:

- HTTP fetch request.
- Browser HTML request.
- Optional screenshot request shape.
- Base64 response decoding.
- Explicit error type for failed Zyte requests.

### Step 4: Parser Utilities

Add parser utilities that use Scrapling when installed. Keep a fallback path available so local fixture tests can run even if Scrapling changes API shape.

### Step 5: Kijiji Adapter Skeleton

Implement:

- Search URL construction for structured filters.
- Search result card parsing.
- Listing detail parsing.
- Image URL extraction.
- Fixture-backed mode for tests.

### Step 6: Fixture Tests

Create Kijiji-like HTML fixtures:

- Search results page.
- Listing detail page.

Test:

- Search result refs extracted.
- Listing detail fields extracted.
- Images extracted.
- Confidence values are present.

### Step 7: API/Service Wiring

Add a scraping search service that:

- Receives search filters.
- Uses Kijiji adapter.
- Parses fixture or live results.
- Converts parsed listings to existing `ListingSnapshot` domain objects.
- Scores opportunities with existing pricing/scoring code.

## Done Criteria

Milestone 2 is complete when:

- `uv run --extra dev pytest` passes.
- Kijiji fixture search returns listing refs.
- Kijiji fixture detail returns a parsed listing.
- Parsed listing can be converted to a scoreable `ListingSnapshot`.
- API search run can return fixture-backed ranked opportunities through the scraping service.

