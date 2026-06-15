# Implementation Plan: Saved Search Persistence

## Objective

Complete the remaining Milestone 3 workflow by turning `/api/searches` from a placeholder into persisted saved searches that the dashboard can create, select, and re-run.

## Current State

The app currently supports ad-hoc search runs through `POST /api/searches/run`, persisted run history, candidate snapshots, and source status metadata. The `searches` table already exists, but `POST /api/searches` returns a generated UUID without writing to the database. `POST /api/searches/{search_id}/run` uses a hardcoded Honda Civic default when no request body is supplied.

## MVP Scope

Implement:

- Persisted search creation.
- Saved search listing.
- Saved search detail lookup.
- Saved search rerun with no override body.
- `last_run_at` updates after saved-search runs.
- Dashboard saved-search list and save/rerun controls.

Do not implement yet:

- Authentication or multi-dealer account management.
- Saved search update/delete.
- Scheduling.
- Alert delivery.
- Per-saved-search custom scoring settings.

## Backend Design

Use the existing `searches` table.

Because authentication is out of scope, create or reuse a deterministic local dealer account:

- Email: `local-dealer@example.test`
- Display name: `Local Dealer`
- Dealership name: `Local Dealer`

Saved search creation accepts the same user-facing fields as an ad-hoc run:

- `name`
- `natural_language_query`
- `structured_filters`
- `listing_limit`
- `sources`
- `max_candidates`
- `listing_url`
- `vin`
- `include_overpriced`

Store vehicle filters in `structured_filters`. Store run options that do not have dedicated columns in reserved JSON keys:

- `_sources`
- `_max_candidates`
- `_listing_url`
- `_vin`

When running a saved search with no request body:

1. Load `Search` by `search_id`.
2. Rehydrate a `SearchRunRequest`.
3. Execute the same `_run_search_request` path as ad-hoc runs.
4. Update `last_run_at` after successful persistence.

When running with an override body, preserve existing behavior and update `last_run_at` if the path targets an existing saved search.

## API Shape

- `POST /api/searches`
  - Persists and returns saved search metadata.
- `GET /api/searches`
  - Lists saved searches.
- `GET /api/searches/{search_id}`
  - Returns one saved search or `404`.
- `POST /api/searches/{search_id}/run`
  - Runs saved definition when body is omitted.
  - Runs override body when provided.

## Dashboard Design

Add a saved-search panel to the left workflow:

- Button to save the current form.
- Saved search list in the history column.
- Selecting a saved search fills the form.
- Rerun saved search calls `POST /api/searches/{id}/run` without a body.

## Acceptance Criteria

- `POST /api/searches` creates a database row.
- `GET /api/searches` returns saved searches.
- `GET /api/searches/{search_id}` returns persisted run options.
- `POST /api/searches/{search_id}/run` runs without a body and updates `last_run_at`.
- Existing ad-hoc run behavior remains unchanged.
- Dashboard can create, select, and rerun a saved search.
- Full backend test suite passes.
