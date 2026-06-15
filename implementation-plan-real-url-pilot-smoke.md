# Real URL Pilot Smoke Implementation Plan

## Objective

Make the app ready for a real dealer test by adding one repeatable command that exercises the full pasted-listing workflow against the running API.

## Why This Is Next

The product already supports fixture-backed intake, promoted opportunities, decision reports, dashboard feedback, and feedback summaries. The next product risk is live marketplace reliability: pasted Kijiji and AutoTrader URLs must either complete end-to-end or fail with useful diagnostics.

## Scope

Build a pilot smoke runner that:

- Checks `/api/settings/source-health`.
- Requires live URL intake by default.
- Accepts one or more pasted listing URLs.
- Supports an optional URL input file for repeated pilot sessions.
- Posts each URL to `/api/opportunities/from-listing`.
- Generates a decision report for each promoted opportunity.
- Optionally submits placeholder smoke feedback.
- Writes a JSON artifact with opportunity IDs, report IDs, source diagnostics, and errors.

## Out of Scope

- Broad live marketplace discovery.
- User accounts or hosted deployment.
- Automatic VIN lookup.
- Replacing dealer feedback with fake smoke data during actual pilots.

## Acceptance Criteria

- The command fails early when live URL intake is not configured unless fixture mode is explicitly allowed.
- A fixture-mode run can complete locally without Zyte credentials.
- The JSON output includes source health, per-listing status, source diagnostics, report result, and optional feedback result.
- Unit tests cover health gating, success flow, and HTTP error capture.
- Existing full test suite still passes.

## Real Pilot Command

```bash
APP_MODE=pilot SCRAPING_FIXTURE_MODE=false SCRAPING_USE_ZYTE=true ZYTE_API_KEY=... \
uv run python -m app.cli.pilot_smoke \
  --base-url http://127.0.0.1:8000 \
  "https://www.kijiji.ca/..." \
  "https://www.autotrader.ca/..."
```

For a local fixture check:

```bash
uv run python -m app.cli.pilot_smoke \
  --base-url http://127.0.0.1:8002 \
  --allow-fixture \
  "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001"
```
