# Implementation Plan: Source Status and Saved Searches

## Objective

Finish the remaining Milestone 3 dashboard foundations by making search runs explain partial source results and by preparing the path from ad-hoc runs to persisted saved searches.

## Current State

The app can run ad-hoc discovery searches, rank opportunities, persist run history, and display results in the dashboard. However, dealers cannot tell whether a missing source produced no listings, failed to fetch, failed to parse, or was not selected. The `/api/searches` create route is also still a placeholder and does not persist saved search definitions.

## Execution Phases

### Phase 1: Source Status Visibility

Add source-level status metadata to every search run.

Status records should include:

- `source_name`
- `status`: `ok`, `failed`, `empty`, or `skipped`
- `listing_count`
- `url`
- `reason`
- `message`
- `retryable`

Backend work:

- Make multi-source search collection tolerant of one source failing.
- Convert unexpected source exceptions into structured source failures.
- Treat zero parsed listings as an `empty` source status.
- Persist source statuses on `search_runs`.
- Return `source_statuses` from run, run-history, and run-detail APIs.
- Preserve current behavior when every selected source fails by returning a `400` with a useful message.

Dashboard work:

- Show compact source status chips in the run summary.
- Show source health in persisted run history.
- Show source failure messages in the alert area.

### Phase 2: Saved Search Persistence

Persist search definitions behind `/api/searches`.

Backend work:

- Store saved search definitions in the existing `searches` table.
- Add list/detail endpoints for saved searches.
- Allow `POST /api/searches/{search_id}/run` to use the saved definition when no override body is provided.
- Update `last_run_at` after a saved search run.

Dashboard work:

- Add saved search list.
- Add create/update controls for saved searches.
- Add rerun controls from saved searches.

### Phase 3: Dashboard Polish

Add dealer workflow controls that build on saved searches:

- Include/exclude overpriced default.
- Seller contact status.
- Seller notes.
- Source failure drilldown.

## Acceptance Criteria for Phase 1

- A selected source failure no longer discards successful results from another selected source.
- Search run responses include source statuses.
- Persisted run history includes source statuses.
- Dashboard shows source statuses and failure messages.
- Tests cover successful, empty, and failed source statuses.
- Full backend test suite passes.

## Acceptance Criteria for Phase 2

- `POST /api/searches` persists a saved search.
- `GET /api/searches` lists saved searches.
- `GET /api/searches/{search_id}` returns a saved search.
- `POST /api/searches/{search_id}/run` can run without an override body.
- Dashboard can create, select, and rerun saved searches.
