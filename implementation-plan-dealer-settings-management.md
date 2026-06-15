# Implementation Plan: Dealer Settings Management

## Objective

Turn dealer settings from static defaults into a persisted workflow that controls scoring, search caps, alert thresholds, and dashboard defaults.

## Current State

- `dealer_settings` exists in the database schema and ORM.
- `GET /api/settings` returns hardcoded values.
- There is no `PATCH /api/settings`.
- The dashboard has no settings controls.
- `SearchPipeline._dealer_settings()` is hardcoded, so target profit, risk tolerance, preferred brands/models, candidate cap, and image cap do not affect scoring from persisted settings.

## Scope

1. Add a dealer settings service around the default dealer account.
2. Add `GET /api/settings` backed by the database.
3. Add `PATCH /api/settings` for partial updates.
4. Validate:
   - target profit is non-negative
   - risk tolerance is `low`, `medium`, or `high`
   - preferred brands/models are normalized string lists
   - radius, threshold, candidate cap, and image cap stay in safe ranges
5. Pass persisted dealer settings into `SearchPipeline`.
6. Use settings to cap saved-search and ad-hoc run candidate counts.
7. Keep alert thresholds reading the same persisted settings.
8. Add dashboard settings controls and save workflow.
9. Add regression tests for API persistence, scoring integration, dashboard assets, and settings-backed search caps.

## API

`GET /api/settings`

Returns the persisted settings row for the default dealer, creating it if missing.

`PATCH /api/settings`

Accepts partial updates:

- `target_profit_cad`
- `risk_tolerance`
- `preferred_brands`
- `preferred_models`
- `default_search_radius_km`
- `include_overpriced_default`
- `candidate_score_threshold`
- `max_candidate_count`
- `max_images_per_candidate`

## Scoring Integration

Search execution loads dealer settings from the same session and constructs `SearchPipeline` with a domain `DealerSettings` object.

Effects:

- `target_profit_cad` changes max-buy and starting-offer calculations.
- `risk_tolerance` changes risk penalties and score weights.
- `preferred_brands` and `preferred_models` change resale-speed score.
- `max_candidate_count` caps detail enrichment and final candidate count.
- `max_images_per_candidate` caps image analysis.
- `candidate_score_threshold` controls high-score alert generation.

## Dashboard Workflow

Add a settings panel in the search sidebar with compact controls:

- target profit
- risk tolerance
- preferred brands/models
- default radius
- include overpriced default
- candidate score threshold
- max candidates
- max images

On load, the dashboard fetches settings and applies defaults to the search form. Saving settings persists via `PATCH /api/settings`.

## Verification

- Settings API creates and returns default settings.
- PATCH persists values and GET returns them.
- Search runs use persisted candidate cap and target profit.
- Dashboard serves settings controls and client functions.
- Full test suite passes.
