# Implementation Plan: Price-Drop Tracking

## Goal

Persist listing-level price history across repeated saved-search and ad hoc runs, then detect and surface price drops using listing snapshot comparison instead of comparing only transient candidate rows.

## Current Gap

The database already has `listings` and `listing_snapshots`, but search persistence only stores `candidate_snapshots`. The existing alert flow can compare a current candidate with an older candidate, but there is no durable per-listing snapshot chain, no first/latest/previous price summary, and no API-visible price history on candidate results.

## Scope

1. Reuse the existing `listings` table as the canonical listing identity keyed by `source_name` and `canonical_url`.
2. Reuse the existing `listing_snapshots` table as the append-only listing observation history.
3. Record one listing snapshot for every scored candidate persisted into a search run.
4. Compare the new listing snapshot with the latest prior snapshot for the same listing.
5. Attach a compact `price_history` object to each persisted candidate's `pricing_summary`.
6. Generate `price_drop` alerts from listing snapshot history.
7. Keep candidate-row comparison as a compatibility fallback for historical rows that predate price-history persistence.

## Data Flow

1. Search pipeline returns scored opportunities with source name, URL, listing ID, vehicle attributes, mileage, seller type, and current asking price.
2. `persist_search_run()` creates a `search_runs` row.
3. For each scored opportunity:
   - Upsert `listings` by `(source_name, canonical_url)`.
   - Query prior `listing_snapshots` for that listing.
   - Insert a new `listing_snapshots` row.
   - Build `price_history` from prior and current snapshots.
   - Persist `candidate_snapshots.pricing_summary.price_history`.
4. Saved-search alert generation reads `candidate.pricing_summary.price_history` and creates a `price_drop` alert when `is_price_drop` is true.
5. Existing `/api/searches/runs/{run_id}` and candidate detail responses expose the summary through `pricing_summary`.

## Price-History Payload

```json
{
  "listing_record_id": "uuid",
  "latest_listing_snapshot_id": "uuid",
  "previous_listing_snapshot_id": "uuid-or-null",
  "snapshot_count": 2,
  "first_price_cad": 23995,
  "previous_price_cad": 23995,
  "current_price_cad": 22995,
  "lowest_price_cad": 22995,
  "highest_price_cad": 23995,
  "price_drop_amount_cad": 1000,
  "price_drop_percent": 4.17,
  "is_price_drop": true
}
```

## Acceptance Criteria

1. Re-running a search for the same listing creates multiple `listing_snapshots`.
2. A lower repeated price sets `price_history.is_price_drop` to `true`.
3. Candidate run detail and candidate detail APIs include `pricing_summary.price_history`.
4. Saved-search alerts use snapshot-derived old/new prices in `price_drop` metadata.
5. Migration smoke tests continue to assert that `listings` and `listing_snapshots` exist.
6. Existing tests continue to pass for candidate persistence, scheduled refresh, and alerts.

