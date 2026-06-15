# Opportunity Stage Workflow Implementation Plan

## Objective

Complete the next MVP workflow slice by making promoted opportunities actionable after candidate promotion. Dealers should be able to move an opportunity through the documented acquisition stages, update seller follow-up context, and get a clear warning before marking an incomplete opportunity as ready to visit.

## Product Context

The app already supports:

- Persisted discovery search runs.
- Persisted ranked candidate snapshots.
- Candidate workflow state for selected, hidden, seller contact status, and notes.
- Promotion from a candidate snapshot into a durable `Opportunity`.
- DB-backed opportunity list and detail APIs.
- A dashboard rail that shows promoted opportunities.

The remaining gap for this step is post-promotion workflow control. The product requirements specify the opportunity stages and require a missing-data warning before moving to `Ready to Visit`, while still allowing dealer override.

## Scope

Implement:

- `PATCH /api/opportunities/{opportunity_id}/stage`
- `PATCH /api/opportunities/{opportunity_id}/contact`
- Backend validation against `OpportunityStage`.
- Readiness warning metadata in opportunity payloads.
- A missing-data guard for `ready_to_visit`:
  - Without override, keep or move the opportunity at `needs_data`.
  - Return a warning that explains `ready_to_visit` requires override while key data is missing.
  - With override, allow `ready_to_visit` and continue returning readiness warnings.
- Dashboard controls in the promoted opportunities rail:
  - Stage selector.
  - Missing-data warning/override checkbox when relevant.
  - Contact status selector.
  - Seller notes textarea.
  - Save actions that refresh the rail.
- Tests for persistence, validation, unknown IDs, and missing-data guard behavior.
- Backend README API examples for the new endpoints.

## Out of Scope

- New database columns or migrations.
- Full report generation.
- Comparable/pricing/risk re-analysis tables.
- Appointment scheduling or notifications.
- Authentication and multi-dealer authorization.

## API Contract

### Stage Update

`PATCH /api/opportunities/{opportunity_id}/stage`

Request:

```json
{
  "stage": "ready_to_visit",
  "override_missing_data_warning": false
}
```

Response:

Returns the full opportunity payload. If `stage` is `ready_to_visit`, missing key data exists, and no override is supplied, the persisted stage is `needs_data` and the response includes:

```json
{
  "stage_update_warning": "missing_key_data_requires_override"
}
```

### Contact Update

`PATCH /api/opportunities/{opportunity_id}/contact`

Request:

```json
{
  "seller_contact_status": "appointment_set",
  "seller_notes": "Seller can meet Saturday morning."
}
```

Response:

Returns the full opportunity payload after persistence.

## Opportunity Payload Additions

All opportunity payloads include:

- `readiness_warnings`: list of active warnings.
- `ready_to_visit_blocked`: `true` when missing key data exists and stage is not already overridden to `ready_to_visit`.
- `stage_update_warning`: only present on stage-update responses when the requested transition was blocked.

## Backend Steps

1. Add service functions to update opportunity stage and contact fields.
2. Add a helper that returns readiness warnings from `missing_key_data`.
3. Add API request models and routes in `app/api/routes/opportunities.py`.
4. Keep the implementation schema-free because existing `opportunities` columns already cover this workflow.

## Dashboard Steps

1. Replace the promoted opportunity rail cards with editable cards.
2. Add stage and contact controls per opportunity.
3. Show missing-key-data tags and readiness warnings.
4. Show an override checkbox only when the selected stage is `ready_to_visit` and the opportunity has missing key data.
5. Refresh opportunity state after a successful update.

## Tests

Add integration coverage for:

- Stage update persists and is visible in opportunity detail.
- Contact update persists and is visible in list/detail responses.
- Unknown opportunity returns `404`.
- Invalid stage returns FastAPI/Pydantic validation error.
- Ready-to-visit without override is held at `needs_data` with warning.
- Ready-to-visit with override persists `ready_to_visit`.

## Acceptance Criteria

- `uv run --extra dev pytest` passes.
- Dashboard can update promoted opportunity stage/contact state without rerunning a search.
- The local dashboard server runs at `http://127.0.0.1:8002/dashboard/`.
- A smoke test can promote a fixture candidate, update contact info, exercise the ready-to-visit warning, and then override it.
