# Report Freshness and Visit Checklist Implementation Plan

## Objective

Make generated decision reports actionable and lifecycle-aware. After a report exists, workflow edits should mark the latest report stale, and dealers should be able to track the pre-visit checklist items that determine whether an opportunity is ready for a visit or offer.

## Current State

The app already supports:

- Candidate promotion to durable opportunities.
- Opportunity stage/contact updates.
- Versioned decision report generation.
- Latest report retrieval and HTML rendering.
- Dashboard controls for generating/opening reports.

The gap is that reports remain static snapshots with no freshness signal, and the required pre-visit checks are only free-text next actions.

## Scope

Implement:

- Persisted `visit_checklist` JSON on `opportunities`.
- `PATCH /api/opportunities/{opportunity_id}/visit-checklist`.
- Latest report summary in opportunity list/detail payloads.
- Stale latest report behavior when stage, contact, notes, or checklist changes.
- Report JSON and HTML support for checklist completion/missing items.
- Dashboard checklist controls inside promoted opportunity cards.
- Tests for checklist persistence, stale report marking, latest report summary, and report content.
- Alembic migration for the new column.

## Visit Checklist Fields

The initial MVP checklist is:

- `vin_confirmed`
- `service_records_requested`
- `lien_status_checked`
- `history_report_checked`
- `extra_photos_requested`
- `visit_appointment_set`

All values default to `false`.

## API Contract

`PATCH /api/opportunities/{opportunity_id}/visit-checklist`

Request:

```json
{
  "vin_confirmed": true,
  "service_records_requested": true,
  "extra_photos_requested": true
}
```

Response:

Returns the full opportunity payload including:

```json
{
  "visit_checklist": {
    "vin_confirmed": true,
    "service_records_requested": true,
    "lien_status_checked": false,
    "history_report_checked": false,
    "extra_photos_requested": true,
    "visit_appointment_set": false
  },
  "latest_report": {
    "id": "...",
    "version": 1,
    "status": "stale",
    "recommendation": "buy_only_cheap"
  }
}
```

## Freshness Rules

- Generating a report creates a new latest report with status computed from current opportunity state.
- Updating opportunity stage marks the latest report stale.
- Updating contact status or seller notes marks the latest report stale.
- Updating checklist state marks the latest report stale.
- If no report exists, updates simply persist workflow/checklist state.

## Dashboard Steps

- Show latest report version/status on each promoted opportunity card.
- Render checklist checkboxes in each promoted opportunity card.
- Add a `Save Checklist` action.
- Keep existing `Generate Report` and `Open Latest` actions.

## Report Steps

- Include `visit_checklist` in `report_json`.
- Include completed and missing checklist labels in the printable HTML report.
- Add missing checklist items to next actions.

## Acceptance Criteria

- Alembic upgrade head includes `opportunities.visit_checklist`.
- `uv run --extra dev pytest` passes.
- HTTP smoke can promote a candidate, generate a report, update checklist, see latest report marked `stale`, then generate a fresh report containing checklist state.
