# Implementation Plan: Scheduled Saved-Search Refresh

## Objective

Turn persisted saved searches into monitorable acquisition searches that can refresh automatically on a configured cadence, while keeping manual reruns and existing search-run history unchanged.

## Current State

- Saved searches are persisted in `searches`.
- The schema already includes `scheduled`, `schedule_cron`, and `last_run_at`.
- `POST /api/searches/{search_id}/run` can rerun a saved search and persists a normal `search_run`.
- There is no scheduler service, CLI runner, background monitor, or UI/API support for choosing refresh frequency.

## Scope

1. Reuse existing schema fields instead of adding a migration.
2. Expose schedule settings through saved-search create/update responses.
3. Share search execution between API-triggered and scheduler-triggered runs.
4. Add a due-search scheduler service.
5. Add an operational one-shot CLI runner.
6. Add an optional in-process FastAPI monitor, disabled by default.
7. Add dashboard controls for saved-search scheduling.
8. Add focused regression tests.

## Schedule Format

MVP schedules use the existing `schedule_cron` text field and support:

- `daily`
- `hourly`
- `every:Nminutes`
- `every:Nhours`
- `every:Ndays`
- `*/N * * * *`
- `0 */N * * *`
- `M H * * *`

The scheduler treats these as intervals from `last_run_at`. Searches with `scheduled=true` and no `last_run_at` are due immediately.

## Execution Flow

1. `list_due_saved_searches` loads scheduled searches ordered by oldest run first.
2. `is_saved_search_due` resolves the saved schedule to an interval.
3. `execute_scheduled_saved_search_refresh` builds a normal saved-search run payload.
4. Shared `execute_search_run` runs the same pipeline used by the API.
5. The run is persisted to `search_runs` and candidate snapshots.
6. `last_run_at` is updated through the existing saved-search service.
7. The scheduler returns a structured summary for logs, tests, and cron output.

## Operations

- One-shot runner:
  `python -m app.cli.refresh_saved_searches`
- Optional app monitor:
  set `SAVED_SEARCH_REFRESH_ENABLED=true`.
- Poll interval:
  `SAVED_SEARCH_REFRESH_POLL_SECONDS=3600`.
- Batch limit:
  `SAVED_SEARCH_REFRESH_BATCH_LIMIT=25`.
- Default schedule when a scheduled search has no value:
  `SAVED_SEARCH_REFRESH_DEFAULT_SCHEDULE=daily`.

## Verification

- Saved-search create response includes `scheduled` and `schedule_cron`.
- Saved-search schedule can be updated with `PATCH /api/searches/{search_id}`.
- Invalid schedule strings are rejected.
- Due scheduled searches create normal persisted search runs.
- Non-due scheduled searches are skipped.
- Dashboard static tests verify schedule controls are shipped.
