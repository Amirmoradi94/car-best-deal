# Implementation Plan: Candidate Workflow State

## Objective

Start Milestone 4 by making ranked candidates actionable inside the dashboard. Dealers need to mark which listings deserve deeper analysis, hide weak results from the active shortlist, and record basic seller follow-up context.

## Current State

Search runs persist ranked `candidate_snapshots` with pricing, risk, relevance, images, and confidence data. The dashboard can load a candidate detail view, but candidate state is read-only. There is no persisted way to select a candidate, hide it from the active shortlist, record seller contact status, or save notes.

## MVP Scope

Add workflow state to `candidate_snapshots`:

- `selected`: candidate is selected for deeper analysis.
- `hidden`: candidate is hidden from the active shortlist.
- `seller_contact_status`: basic acquisition follow-up status.
- `seller_notes`: free-text dealer notes.

Add API support:

- `PATCH /api/searches/runs/{run_id}/candidates/{candidate_id}`
- Request body accepts any subset of:
  - `selected`
  - `hidden`
  - `seller_contact_status`
  - `seller_notes`
- Response returns the updated candidate payload.

Add dashboard support:

- Select/unselect candidate.
- Hide/unhide candidate.
- Toggle hidden candidates in the list.
- Edit seller contact status.
- Save seller notes.

## Out of Scope

- Creating durable `Opportunity` rows from selected candidates.
- Manual candidate add by URL.
- Comparable editing.
- Full report generation.
- Notifications or scheduling.

## Data Model

Add columns to `candidate_snapshots`:

- `selected boolean not null default false`
- `hidden boolean not null default false`
- `seller_contact_status text null`
- `seller_notes text null`

Existing candidate snapshots default to unselected and visible.

## Acceptance Criteria

- Candidate update endpoint persists selected/hidden/contact/notes fields.
- Candidate detail response includes the workflow fields.
- Run detail response includes the workflow fields for list rendering.
- Dashboard can update and refresh candidate state without rerunning the search.
- Hidden candidates are excluded by default unless the dashboard toggle is enabled.
- Full backend test suite passes.
