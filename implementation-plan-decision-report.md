# Decision Report Implementation Plan

## Objective

Add the first persisted dealer-facing decision report for promoted opportunities. This completes the next functional step after opportunity promotion and stage workflow: turn the saved candidate evidence into a report that answers whether the dealer should pursue, inspect, offer on, or pass on the vehicle.

## Current State

The app already supports:

- Persisted search runs and candidate snapshots.
- Promotion from candidate snapshot to durable `Opportunity`.
- Opportunity stage and seller contact workflow.
- `decision_reports` table in the existing schema.
- A placeholder `/api/reports/{report_id}` route that still returns fixture data.

## Scope

Implement:

- `POST /api/opportunities/{opportunity_id}/reports`
- `GET /api/opportunities/{opportunity_id}/reports/latest`
- `GET /api/opportunities/{opportunity_id}/reports/latest/html`
- DB-backed `GET /api/reports/{report_id}`
- A deterministic report builder from existing opportunity and candidate data.
- Dashboard controls to generate and open the latest report.
- Tests for report creation, latest retrieval, HTML rendering, report ID lookup, missing opportunity, and missing report cases.
- Backend README examples.

## Out of Scope

- PDF generation.
- CSV export.
- LLM-generated narrative.
- New pricing/risk analysis tables.
- Report sharing, permissions, or authentication.
- Stale report invalidation after every opportunity edit.

## Report Data Contract

Persist one `DecisionReport` row per generated version:

- `opportunity_id`
- `version`
- `status`
- `recommendation`
- `report_json`
- `confidence_by_section`

`report_json` includes:

- `summary`
- `vehicle`
- `listing`
- `pricing`
- `risk`
- `image_review`
- `workflow`
- `seller`
- `next_actions`
- `evidence`

## Status Rules

- `full`: no missing key data and pricing is not preliminary.
- `partial`: missing key data remains.
- `preliminary`: pricing is preliminary but no missing key data is recorded.

The first slice keeps these rules deterministic and testable.

## Recommendation Rules

Use the existing candidate recommendation when available. If no linked candidate exists:

- `pass` for overpriced opportunities.
- `needs_more_data` when missing key data exists.
- `buy_only_cheap` otherwise.

## HTML View

The HTML endpoint returns a compact, printable report page containing:

- Recommendation and status.
- Vehicle/listing facts.
- Pricing numbers.
- Missing verification and risk tags.
- Image-risk notes.
- Seller notes and current stage.
- Recommended next actions.

## Dashboard Steps

Add promoted-opportunity controls:

- `Generate Report`
- `Open Latest Report`

After a report is generated, show the generated version/status and open the HTML view in a new browser tab.

## Acceptance Criteria

- `uv run --extra dev pytest` passes.
- A promoted fixture candidate can generate a persisted report.
- Latest report retrieval returns the newest version.
- HTML view renders the report without relying on client-side JavaScript.
- Dashboard can generate and open reports for promoted opportunities.
