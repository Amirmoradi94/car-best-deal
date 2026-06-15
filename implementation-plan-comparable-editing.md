# Comparable Editing Implementation Plan

## Goal

Let dealers remove bad comparables from a promoted opportunity, recalculate retail value and max-buy price from the remaining included comparables, and create a new versioned decision report after the edit.

## Backend Scope

1. Preserve comparable provenance.
   - Add comparables to `ScoredOpportunity`.
   - Store scored comparables in candidate `pricing_summary`.
   - Materialize those comparables into `comparable_listings` when a candidate is promoted.

2. Support comparable exclusion.
   - Add `excluded_reason` to `ComparableListingModel`.
   - Add Alembic migration after the dealer-corrections migration.
   - Add comparable listing payloads with included/excluded state.

3. Recalculate pricing.
   - Build a target `ListingSnapshot` from the promoted candidate.
   - Build included domain comparables from `comparable_listings`.
   - Reuse cost assumptions from the existing pricing summary.
   - Recalculate retail low/mid/high, max-buy, starting offer, and comparable count.
   - Persist a new `pricing_analyses` row with incremented version.
   - Update the candidate pricing summary and opportunity score/preliminary/overpriced state.

4. API workflow.
   - `GET /api/opportunities/{opportunity_id}/comparables`
   - `PATCH /api/comparables/{comparable_id}`
   - `POST /api/opportunities/{opportunity_id}/recalculate`
   - Excluding a comparable recalculates pricing and immediately creates a new report version.

5. Report integration.
   - Include comparable summary in report JSON and HTML.
   - Continue using candidate `pricing_summary` as the report pricing source after recalculation.

## Frontend Scope

1. Add a comparable-editing panel to promoted opportunity cards.
2. Show included and excluded comparable counts plus latest pricing values.
3. Load comparables on demand.
4. Allow removing included comparables with a reason.
5. Show the newly generated report version after removal.

## Tests

1. Migration smoke validates `excluded_reason` and new migration head.
2. API tests validate:
   - promoted opportunities expose comparables
   - removing a comparable flips `included` to false
   - recalculated pricing has a lower comparable count
   - candidate/opportunity pricing changes are returned
   - latest report version increments after removal
   - removing the final included comparable is rejected
3. Dashboard static tests validate UI handlers and CSS hooks.

## Verification

- `python3 -m compileall app tests`
- Focused tests:
  - `uv run pytest -q tests/test_migrations.py tests/test_previsit_persistence.py tests/test_dashboard.py tests/test_search_pipeline.py`
- Full suite if focused tests pass.
