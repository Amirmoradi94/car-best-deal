# Pilot Feedback Loop Implementation Plan

## Objective

Add structured pilot feedback capture so real-world tests produce product evidence. The goal is to let a dealer record whether an opportunity report was useful, accurate, missing important information, or led to a concrete acquisition decision.

## Current State

The app supports:

- Direct listing intake from Kijiji/AutoTrader URLs.
- Promoted opportunity workflow.
- Visit checklist and stale report lifecycle.
- Versioned decision reports.
- Source diagnostics and pilot mode.

The missing piece is a review loop that captures what happened after a dealer used the report.

## Scope

Implement:

- `opportunity_feedback` table.
- `POST /api/opportunities/{opportunity_id}/feedback`.
- `GET /api/opportunities/{opportunity_id}/feedback`.
- `GET /api/feedback`.
- `GET /api/feedback/summary`.
- Dashboard feedback form per promoted opportunity.
- Dashboard pilot feedback summary.
- Tests for feedback persistence, report linkage, summary aggregation, invalid values, and unknown opportunities.

## Feedback Fields

Persist:

- `opportunity_id`
- `report_id`
- `report_version`
- `usefulness_rating` from 1 to 5.
- `accuracy_rating` from 1 to 5.
- `dealer_decision`: `undecided`, `pursue`, `pass`, `contacted`, `visited`, `offered`, `bought`.
- `missing_info`: list of strings.
- `incorrect_info`: list of strings.
- `notes`: free-form text.

When feedback is submitted, link it to the latest report if one exists.

## Dashboard UX

Each promoted opportunity card gets a compact pilot feedback form:

- Usefulness rating.
- Accuracy rating.
- Decision.
- Missing info.
- Incorrect info.
- Notes.
- Save feedback.

The right rail also gets a pilot summary panel showing:

- Total feedback entries.
- Tested opportunities.
- Average usefulness.
- Average accuracy.
- Decision counts.
- Common missing info.
- Common incorrect info.

## Acceptance Criteria

- `uv run --extra dev pytest` passes.
- A promoted opportunity can store feedback linked to its latest report.
- Feedback list endpoints return newest first.
- Summary endpoint aggregates pilot evidence.
- Dashboard can submit feedback and refresh the summary.
