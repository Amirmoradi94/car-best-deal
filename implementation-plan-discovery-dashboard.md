# Implementation Plan: Discovery Dashboard

## Objective

Build the first dealer-facing dashboard for the existing backend search workflow. The dashboard should make the current fixture-backed and live-backed search API usable without requiring curl commands or direct API documentation.

## Current Backend Capabilities

The backend already supports:

- Running ad-hoc searches through `POST /api/searches/run`.
- Selecting `kijiji`, `autotrader`, or `both` as sources.
- Passing natural-language query text, structured filters, listing limits, and candidate caps.
- Running single-listing URL analysis with optional VIN.
- Persisting search runs and ranked candidate snapshots.
- Listing previous search runs through `GET /api/searches/runs`.
- Fetching run details and candidate details through run-history endpoints.

## MVP Dashboard Scope

The first dashboard includes:

- Search creation form.
- Natural-language query input.
- Structured inputs for make, model, year range, city, province, price cap, mileage cap, and radius.
- Source selector for both Kijiji and AutoTrader.
- Optional single-listing URL and VIN fields.
- Ranked opportunity list.
- Overpriced visibility toggle.
- Source, score, recommendation, price, max-buy-price, image-risk, missing-data, and relevance indicators.
- Persisted run history panel.
- Candidate detail panel.
- Source failure or API error display.

The first dashboard excludes:

- Authentication.
- Saved search scheduling.
- Alert creation and email delivery.
- Manual candidate add/remove.
- Comparable editing and recalculation.
- PDF/CSV report export.
- VIN-only analysis.

## Technical Approach

Serve a lightweight static dashboard from FastAPI at `/dashboard/`.

This is the lowest-friction next step because the repository currently has no frontend scaffold. A static HTML/CSS/JavaScript dashboard keeps the milestone focused on product workflow validation and avoids introducing a package manager, bundler, frontend test runner, and deployment split before the UI surface is proven.

Use:

- `app/static/dashboard/index.html`
- `app/static/dashboard/styles.css`
- `app/static/dashboard/app.js`
- FastAPI `StaticFiles` mount at `/dashboard`

## User Workflow

1. Dealer opens `/dashboard/`.
2. Dealer enters either a broad search or a single listing URL.
3. Dashboard calls `POST /api/searches/run`.
4. Ranked candidates render immediately.
5. Dealer can hide/show overpriced results.
6. Dealer selects a candidate to inspect pricing, risk, missing data, image evidence, and source URL.
7. Run history refreshes from persisted search runs.
8. Dealer can reload previous runs.

## Acceptance Criteria

- `/dashboard/` returns the dashboard HTML.
- The dashboard can run the default Honda Civic fixture-backed search.
- The dashboard renders ranked opportunities from `ranked_opportunities`.
- The dashboard can fetch and display previous runs.
- The dashboard can fetch and display candidate detail.
- API errors are visible in the UI.
- The normal backend test suite passes.

## Follow-On Work

After this dashboard is usable, the next likely tasks are:

- Add saved-search persistence instead of only ad-hoc runs.
- Add source health and source failure details to persisted run responses.
- Add manual candidate selection state.
- Add report-generation endpoints and a report preview panel.
- Move to a dedicated frontend stack only after the first dashboard workflow stabilizes.
