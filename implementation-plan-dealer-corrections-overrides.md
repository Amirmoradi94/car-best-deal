# Dealer Corrections / Explicit Overrides Implementation Plan

## Goal

Add a dealer-facing workflow to correct bad parsed or verified fields on promoted opportunities and carry those explicit overrides into future decision reports.

## Scope

- Persist dealer corrections in the existing architecture's `dealer_corrections` model shape.
- Support corrections for core vehicle/listing facts and verification facts:
  - `vehicle.year`
  - `vehicle.make`
  - `vehicle.model`
  - `vehicle.trim`
  - `vehicle.vin`
  - `vehicle.mileage_km`
  - `listing.asking_price_cad`
  - `history.accident_history_status`
  - `title.lien_status`
- Keep original scraped candidate snapshots intact for auditability.
- Apply the latest `apply_to_future=true` correction per field when generating new decision reports.
- Mark the latest report stale whenever a correction is saved.
- Show correction history and corrected fields in the opportunity response and dashboard.

## Backend Work

1. Add `DealerCorrection` SQLAlchemy model.
   - Follow architecture fields: dealer account, opportunity, entity type/id, field name, old/new JSON values, reason, future application, timestamps.
   - Add index for `(dealer_account_id, entity_type, field_name)`.

2. Add Alembic migration.
   - Create `dealer_corrections`.
   - Keep SQLite-compatible JSON column types.
   - Update migration smoke test expected head.

3. Add `app/services/dealer_corrections.py`.
   - Validate supported entity/field pairs.
   - Normalize numeric/string/status values.
   - Resolve old values from candidate snapshot, report-derived verification state, or existing latest correction.
   - Create correction rows.
   - List corrections newest-first.
   - Build latest active override map and payload summaries.

4. Add opportunity API endpoints.
   - `POST /api/opportunities/{opportunity_id}/corrections`
   - `GET /api/opportunities/{opportunity_id}/corrections`
   - Return correction payloads plus refreshed opportunity payload on create.
   - Mark latest decision report stale on create.

5. Integrate reports.
   - Load corrections in `create_decision_report`.
   - Overlay vehicle/listing fields in `report_json`.
   - Overlay history/lien verification status where applicable.
   - Remove `vehicle_history` or `lien_verification` missing-data blockers when explicit dealer statuses prove the check is clear.
   - Add `evidence.dealer_corrections` and a report HTML section.

## Frontend Work

1. Add a compact “Dealer corrections” group to each promoted opportunity card.
2. Provide controls for trim, mileage, accident history, lien status, and reason.
3. Save non-empty corrections through the new endpoint.
4. Render a latest-corrections summary in the card.
5. Ensure report stale state updates in the UI response.

## Tests

1. Migration smoke test covers the new table/columns and new head revision.
2. API tests cover:
   - creating/listing corrections
   - stale report marking
   - corrected trim/mileage in generated report
   - corrected lien/history statuses in report verification/missing-data handling
   - validation and 404 cases
3. Dashboard static tests cover correction controls, handlers, and CSS hooks.

## Verification

- `python3 -m compileall app tests`
- Focused tests:
  - `uv run pytest -q tests/test_migrations.py tests/test_previsit_persistence.py tests/test_dashboard.py`
- Full suite if focused tests pass.
