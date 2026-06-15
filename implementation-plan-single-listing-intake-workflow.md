# Single-Listing Intake Workflow Implementation Plan

## Objective

Make the app useful when a dealer starts from one known listing URL instead of a broad discovery search. The dealer should be able to paste a Kijiji or AutoTrader listing URL, optionally attach a VIN, analyze it against comparables, promote it directly into the opportunity workflow, and generate the existing decision report/checklist from that opportunity.

## Current State

The backend already supports single-listing analysis through `POST /api/searches/run` when `listing_url` is present. That path:

- Detects Kijiji or AutoTrader from the URL.
- Fetches/parses the target listing.
- Builds comparable search filters from the listing.
- Scores one ranked candidate.
- Persists a normal search run and candidate snapshot.

The gaps:

- The dashboard still treats this like a broad search.
- Promotion requires a separate manual step after analysis.
- API responses do not clearly expose intake mode.
- A provided VIN is not reflected in the opportunity checklist.

## Scope

Implement:

- `POST /api/opportunities/from-listing`
- Explicit intake metadata in search run responses:
  - `intake_mode`: `single_listing` or `discovery`
  - `listing_url`
  - `vin`
  - `direct_promote_available`
- Candidate payload metadata for single-listing candidates.
- Promotion behavior that marks `visit_checklist.vin_confirmed = true` when the promoted candidate has a VIN.
- Dashboard `Analyze + Promote` action for listing URL intake.
- Report JSON evidence field for intake mode and source URL.
- Tests for Kijiji and AutoTrader URL intake through direct promotion and report generation.

## API Contract

`POST /api/opportunities/from-listing`

Request:

```json
{
  "name": "Single listing intake",
  "listing_url": "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
  "vin": "2HGFC2F59LH000001",
  "sources": "both",
  "listing_limit": 25
}
```

Response:

```json
{
  "status": "promoted",
  "run_id": "...",
  "candidate_id": "...",
  "intake_mode": "single_listing",
  "opportunity": {
    "id": "...",
    "visit_checklist": {
      "vin_confirmed": true
    }
  }
}
```

## Dashboard Steps

- Add an `Analyze + Promote` button near the existing search actions.
- Enable it when a listing URL is present.
- On success:
  - Load the persisted run.
  - Select the promoted candidate.
  - Refresh the promoted opportunity rail.
  - Show the created opportunity status.

## Acceptance Criteria

- `uv run --extra dev pytest` passes.
- Existing broad search still works.
- Existing single-listing run still returns one candidate.
- Direct single-listing intake creates one persisted run, one candidate, and one opportunity.
- VIN-provided direct intake sets `visit_checklist.vin_confirmed`.
- Decision report evidence includes `intake_mode: single_listing`.
