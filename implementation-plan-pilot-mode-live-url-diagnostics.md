# Pilot Mode and Live URL Diagnostics Implementation Plan

## Objective

Move the app closer to real-world testing by making source mode explicit and diagnostics visible. The first pilot target is manually pasted listing URLs, not broad live discovery, so dealers can test real workflow quality while source reliability is still being validated.

## Current State

The app supports:

- Fixture-backed discovery and single-listing analysis.
- Direct listing URL intake and promotion.
- Source status persistence on search runs.
- Dashboard source status display.

The gap is operational safety for real tests:

- Fixture/live/pilot state is implicit.
- Source statuses do not expose fetch mode or app mode.
- Live URL failure diagnostics are not prominent.
- Broad live discovery can accidentally run when fixture mode is disabled.

## Scope

Implement:

- `APP_MODE=fixture | pilot | live`.
- Pilot policy:
  - `pilot` permits live fetching only for manually pasted listing URLs.
  - Broad discovery in `pilot` is forced to fixture-backed behavior unless explicitly moved to `live`.
- Source diagnostics metadata on every source status:
  - `app_mode`
  - `fixture_mode`
  - `fetch_method`
  - `source_role`
  - `status_code`
  - `rendered`
  - `parser`
- `GET /api/health/sources`.
- Dashboard badges/messages for app mode and source diagnostics.
- Tests for app mode validation, pilot URL diagnostics, fixture diagnostics, and health endpoint.

## Out of Scope

- Real external smoke tests requiring `ZYTE_API_KEY`.
- Full source snapshot storage in a new table.
- Broad live discovery hardening.
- Authentication, rate limits, or dealer accounts.

## Acceptance Criteria

- `uv run --extra dev pytest` passes.
- Search run source statuses include app mode and fetch diagnostics.
- `/api/health/sources` reports source readiness and mode policy.
- Dashboard source status cards show fixture/pilot/live diagnostic labels.
- Existing fixture-mode workflows remain deterministic.
