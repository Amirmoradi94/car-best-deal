# Search Request API Implementation Plan

## Objective

Replace the hardcoded Honda Civic run path with an MVP search request contract that lets a dealer submit real discovery criteria before physical vehicle visits.

## MVP Scope

The API should support:

- Natural language query, such as `2020 Honda Civic Montreal`.
- Structured filters for make, model, year range, price range, mileage max, city/province, radius, seller type, and listing limit.
- Source mode: `both`, `kijiji`, or `autotrader`.
- Final-candidate enrichment cap, limited to 50 candidates.
- Persisted run creation and retrieval through the existing run history endpoints.
- Explicit handling for `listing_url` and `vin` inputs so the public contract is clear, without silently pretending single-car analysis is complete.

## API Shape

Add:

- `POST /api/searches/run`

Keep:

- `POST /api/searches/{search_id}/run`

Both endpoints should use the same request model. The ad-hoc endpoint generates a search ID. The existing endpoint keeps the provided search ID.

## Request Fields

- `name`
- `natural_language_query`
- `structured_filters`
- `listing_limit`
- `sources`
- `max_candidates`
- `listing_url`
- `vin`

## Execution Flow

1. Validate request.
2. Reject `listing_url` or `vin` single-car analysis with an explicit `501` until its comparable-building path exists.
3. Normalize request into `SearchFilters`.
4. Run pre-visit candidate search using selected sources.
5. Enrich only the capped final candidates.
6. Persist the run and ranked candidate snapshots.
7. Return `run_id`, status, normalized filters, selected sources, and ranked opportunities.

## Pipeline Changes

Add source selection to:

- `run_multi_source_batch_search`
- `run_previsit_candidate_search`

Default remains both sources to keep existing callers and tests compatible.

## Done Criteria

- API no longer hardcodes Honda Civic for request-based runs.
- Existing route remains backward compatible.
- Tests cover structured input, natural-language input, source selection, persistence, and unsupported single-car input.
- Full backend test suite passes.
