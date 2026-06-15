# Single-Car Analysis Implementation Plan

## Objective

Support the MVP flow where a dealer pastes a Kijiji or AutoTrader listing URL and receives the same pre-visit pricing, risk, image-risk, and persistence output as a discovery run.

## Scope

Implemented now:

- Detect listing source from URL.
- Fetch and parse the listing detail page through the matching adapter.
- Merge an optional VIN into the parsed target listing.
- Build a comparable search from the target listing year/make/model/location.
- Fetch comparable listings from selected sources.
- Score the target listing against those comparables.
- Run image-risk analysis on the target listing.
- Persist the result as a normal `SearchRun` with one ranked candidate.

Deferred:

- VIN-only lookup without a listing URL. This needs a VIN decoding/history provider and a source-discovery strategy.
- Manual comparable override.
- Persisting supporting comparable rows separately from the candidate pricing summary.

## API Behavior

`POST /api/searches/run` and `POST /api/searches/{search_id}/run` should:

- Use discovery flow when no `listing_url` is provided.
- Use single-car analysis when `listing_url` is provided.
- Return `501` for VIN-only input until a VIN data provider exists.
- Return `400` for unsupported listing domains.

## Pipeline Flow

1. Detect source adapter from URL.
2. Fetch listing detail.
3. Parse detail into `ListingSnapshot`.
4. Apply optional VIN.
5. Run image-risk analysis on the target.
6. Build comparable `SearchFilters` from target vehicle profile.
7. Run batch search against requested comparable sources.
8. Score target listing against comparable pool.
9. Return zero or one `ScoredOpportunity`.

## Done Criteria

- Kijiji URL fixture path returns one persisted candidate.
- AutoTrader URL fixture path returns one persisted candidate.
- Unsupported domain returns `400`.
- VIN-only input returns `501`.
- Full backend test suite passes.
