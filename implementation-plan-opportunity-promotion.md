# Implementation Plan: Candidate Promotion to Opportunity

## Objective

Create the durable workflow bridge from ranked candidate snapshots to real dealer opportunities. This makes selected candidates usable by future report generation, stage transitions, alerts, and acquisition workflow screens.

## Current State

The app persists ranked `candidate_snapshots` inside each search run. Candidates can be selected, hidden, and annotated with seller contact status and notes. The `opportunities` table exists, but `/api/opportunities` currently returns fixture-backed placeholder data and candidates are not linked to opportunities.

## MVP Scope

Implement:

- Promote one candidate snapshot into one durable `Opportunity`.
- Store the created `opportunity_id` on the candidate snapshot.
- Make promotion idempotent.
- Replace fixture-backed opportunity list/detail APIs with DB-backed APIs.
- Add dashboard controls to promote selected candidates and view promoted opportunities.

Do not implement yet:

- Full `Listing`, `ListingSnapshot`, and `VehicleProfile` canonicalization during promotion.
- Opportunity stage update endpoints.
- Report generation.
- Comparable editing.
- Alert creation.

## Data Model

Add to `candidate_snapshots`:

- `opportunity_id text null references opportunities(id)`

For the first promotion slice, the durable `Opportunity` stores workflow fields that already exist:

- `dealer_account_id`
- `stage`
- `deal_score`
- `preliminary`
- `missing_key_data`
- `is_overpriced`
- `candidate_selected`
- `seller_contact_status`
- `seller_notes`

The candidate snapshot remains the evidence-rich record for:

- listing/source identity
- vehicle fields
- pricing summary
- risk summary
- image URLs
- relevance metadata
- confidence by section

## API Shape

- `POST /api/searches/runs/{run_id}/candidates/{candidate_id}/promote`
  - Creates an opportunity if one does not exist.
  - Returns the linked opportunity payload.
  - If already promoted, returns the existing opportunity payload.

- `GET /api/opportunities`
  - Lists DB-backed promoted opportunities.

- `GET /api/opportunities/{opportunity_id}`
  - Returns opportunity detail, including linked candidate snapshot evidence when available.

## Dashboard Changes

- Add `Promote to Opportunity` button in candidate detail.
- Show already-promoted opportunity ID/state.
- Add promoted opportunities panel in the right rail.
- Allow opening opportunity detail from the panel.

## Acceptance Criteria

- Promoting a candidate creates exactly one opportunity.
- Re-promoting the same candidate is idempotent.
- Seller notes/contact status carry over.
- Candidate payload includes `opportunity_id`.
- Opportunity list/detail endpoints are DB-backed.
- Dashboard can promote and display opportunities.
- Full backend test suite passes.
