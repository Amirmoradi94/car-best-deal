# Vehicle History Ingestion Plan

## Goal

Close the current vehicle-history gap for real pre-visit testing by letting an opportunity store a manually entered, CARFAX Canada-derived, seller-document, auction-report, or future API payload and then use that evidence in the decision report.

## Scope for this slice

1. Persist one or more history profiles per opportunity.
2. Accept normalized history fields:
   - accident claims
   - registration events
   - owner count
   - odometer records and odometer issue flag
   - service records and service-record count
   - import history
   - title brand
   - salvage, flood, fire, and theft statuses
   - source metadata and raw payload
3. Mark `vehicle_history` as resolved on the opportunity once history evidence is ingested.
4. Mark the visit checklist `history_report_checked` item complete.
5. Mark the latest decision report stale when history changes.
6. Include the latest history profile in newly generated reports, verification status, risk factors, next actions, and report HTML.
7. Keep lien/title verification and recall checks separate. Title-brand and damage flags are useful risk evidence, but they do not clear `lien_verification`.

## API Contract

### PUT `/api/opportunities/{opportunity_id}/history`

Creates or updates the latest normalized history profile for an opportunity.

```json
{
  "source_type": "carfax",
  "source_name": "CARFAX Canada",
  "report_identifier": "CFX-123",
  "title_brand": "clean",
  "accident_claims": [
    {
      "date": "2022-04-12",
      "amount_cad": 1400,
      "description": "Rear bumper claim",
      "severity": "minor"
    }
  ],
  "registration_events": [
    {
      "date": "2020-05-10",
      "province": "QC",
      "event": "registered"
    }
  ],
  "owners_count": 2,
  "odometer_records": [
    {
      "date": "2024-11-01",
      "mileage_km": 78200,
      "source": "service"
    }
  ],
  "odometer_issue": false,
  "service_records_count": 8,
  "service_records": [
    {
      "date": "2024-11-01",
      "mileage_km": 78200,
      "description": "Oil service"
    }
  ],
  "import_history": [],
  "salvage_status": "clear",
  "flood_status": "clear",
  "fire_status": "clear",
  "theft_status": "clear",
  "summary": "Minor claim only; regular service records present.",
  "raw_payload": {}
}
```

### GET `/api/opportunities/{opportunity_id}/history`

Returns all history profiles for the opportunity, newest first, plus a `latest` profile.

## Execution Order

1. Add `opportunity_history_profiles` model and migration.
2. Add a `vehicle_history` service for validation-adjacent normalization, payload serialization, and opportunity state updates.
3. Wire opportunity routes for ingestion/retrieval.
4. Update decision-report generation to read the latest history profile.
5. Add tests for migration, API persistence, stale-report behavior, and report output.
6. Run focused tests and the full test suite.
