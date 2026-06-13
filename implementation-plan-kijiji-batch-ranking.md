# Implementation Plan: Kijiji Batch Ranking

## Objective

Connect live Kijiji search results into the ranked opportunity pipeline using real parsed Kijiji data instead of the shared Civic fixture comparable set.

## Scope

This milestone includes:

- Parsing Kijiji search-result structured data into `ParsedListing` objects.
- Converting parsed search listings into `ListingSnapshot` domain objects.
- Creating same-batch comparable listings from the parsed search result set.
- Ranking Kijiji opportunities using the existing pricing and scoring engines.
- Updating the search API to use the batch ranking path.
- Adding tests for synthetic fixtures and live-captured Kijiji fixtures.

This milestone excludes:

- Fetching every listing detail page during search.
- Gemini fallback extraction.
- AutoTrader integration.
- Database persistence.
- Production relevance filtering for noisy Kijiji search results.

## Approach

Use Kijiji search-result data as the first discovery-stage dataset:

1. Fetch search snapshot.
2. Parse structured JSON-LD `ItemList` data when available.
3. Fall back to synthetic selector-based card parsing.
4. Convert each parsed listing to a `ListingSnapshot`.
5. For each listing, use other listings in the same search batch as comparables.
6. Calculate retail range, max buy price, risk, and deal score.
7. Return ranked opportunities.

## Done Criteria

- Search pipeline no longer depends on `fixtures/listings/civic_target.json` for comparables.
- Live Kijiji search fixture produces ranked scored opportunities.
- API search run returns ranked opportunities from parsed Kijiji search data.
- Tests pass.

