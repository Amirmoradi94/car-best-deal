# Backend Quick Start

## Install and Test

Use `uv` from the project root:

```bash
uv run --extra dev pytest
```

## Run API

```bash
uv run uvicorn app.api.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```

## Current Implementation

This includes the Milestone 1 backend slice:

- Domain enums and dataclasses.
- Fixture-backed scoring and pricing.
- Weighted comparable valuation.
- Preliminary max-buy-price calculation.
- Missing VIN/history/lien penalties.
- Overpriced classification.
- FastAPI route skeleton.
- SQLAlchemy model definitions.

Milestone 2 has also started:

- Environment-based scraping config.
- Zyte API client.
- Scraping contracts.
- Kijiji adapter skeleton.
- Kijiji-like HTML fixtures.
- Fixture-backed parser tests.
- Search pipeline that converts parsed listings into scored opportunities.
- Kijiji same-batch ranking using parsed search-result listings as comparables.
- Query relevance filtering so off-query Kijiji results do not rank as first-class opportunities.
- AutoTrader adapter with synthetic and live fixture coverage.
- Combined Kijiji + AutoTrader batch ranking using same-batch comparables across both sources.
- AutoTrader live smoke CLI with search and first-listing detail fixture capture.
- Pre-visit candidate enrichment that fetches detail pages only for the top capped candidates.
- Deterministic image-risk gate that marks missing or thin image sets before Gemini integration.
- Persisted pre-visit search runs and candidate snapshots for history and detail retrieval.
- Persisted per-source search status metadata so partial Kijiji/AutoTrader failures are visible.
- Single-listing URL analysis for Kijiji and AutoTrader using discovered comparables.
- Alembic migration setup with an initial schema migration.
- Docker Compose PostgreSQL runtime for local migration and persistence verification.
- PostgreSQL FastAPI route verification for search run persistence and retrieval.

The app defaults to fixture scraping mode. To prepare for live Zyte-backed fetching, copy `.env.example` to `.env`, set `ZYTE_API_KEY`, and set:

```text
APP_MODE=pilot
SCRAPING_FIXTURE_MODE=false
SCRAPING_USE_ZYTE=true
```

`APP_MODE` supports:

- `fixture`: deterministic local fixtures only.
- `pilot`: live fetching is intended for manually pasted listing URLs first; broad discovery remains fixture-backed unless explicitly moved to live mode.
- `live`: live fetching can be used for all configured scraping paths.

Check source readiness with:

```bash
curl http://127.0.0.1:8000/api/settings/source-health
```

Search run `source_statuses` include diagnostics such as `app_mode`, `fixture_mode`, `fetch_method`, `source_role`, `status_code`, `rendered`, and parser name so pilot testers can tell whether a result came from fixtures or a live source fetch.

## Dealer Settings

Dealer settings are persisted behind `/api/settings` and control scoring, shortlist caps, image analysis caps, alert thresholds, and dashboard defaults.

Read current settings:

```bash
curl http://127.0.0.1:8000/api/settings
```

Update settings:

```bash
curl -X PATCH http://127.0.0.1:8000/api/settings \
  -H 'Content-Type: application/json' \
  -d '{
    "target_profit_cad": 3200,
    "risk_tolerance": "low",
    "preferred_brands": ["Honda", "Toyota"],
    "preferred_models": ["Civic", "Corolla"],
    "default_search_radius_km": 75,
    "include_overpriced_default": false,
    "candidate_score_threshold": 70,
    "max_candidate_count": 25,
    "max_images_per_candidate": 8
  }'
```

`target_profit_cad`, `risk_tolerance`, and preferred brands/models feed the search scoring pipeline. `max_candidate_count` caps pre-visit enrichment even if an individual request asks for more candidates. `max_images_per_candidate` caps image analysis. `candidate_score_threshold` drives high-score alerts.

To enable Gemini-backed image analysis for live pre-visit enrichment, also set:

```text
GEMINI_API_KEY=...
AI_EXTRACTION_ENABLED=true
GEMINI_TEXT_ANALYSIS_ENABLED=false
GEMINI_IMAGE_ANALYSIS_ENABLED=true
GEMINI_MODEL=gemini-3.5-flash
```

The app uses the Gemini `models.generateContent` REST API with image parts and JSON output. If Gemini is disabled, credentials are missing, image fetching fails, or the app runs in fixture mode, the deterministic image-risk gate is used instead.

The broader AI extraction layer uses the same Gemini endpoint for JSON text tasks when `GEMINI_TEXT_ANALYSIS_ENABLED=true` and fixture mode is off. When Gemini text analysis is disabled, deterministic local extractors still produce auditable outputs for listing fallback extraction, listing risk-language detection, comparable relevance checks, vehicle-history text extraction, and report narrative writing. Every AI task writes an `ai_model_outputs` row and stores its input/output JSON in object storage under `ai-model-outputs/{output_id}/`. Audit rows store provider, model, model version, schema name/version, raw output, schema-validated output, per-field confidence values, and source-evidence links. Candidate payloads expose `ai_outputs` references, vehicle-history responses return `ai_extraction`, and decision reports include `report_json.ai_report_narrative` plus evidence-level AI output references.

## Persisted Product Entities

The product requirements map to concrete persisted tables and services:

- `HistoryProfile`: `opportunity_history_profiles` through the vehicle history service.
- `LienProfile`: `lien_profiles`, created from title/lien evidence and document-upload title evidence.
- `ImageAnalysis`: `image_analyses`, created when a candidate is promoted from persisted image-risk facts.
- `CandidateAnalysis`: `candidate_analyses`, created when a candidate is promoted.
- `DealerCorrection`: `dealer_corrections` through the dealer correction service.
- `Alert`: `alerts` through saved-search alert generation and read-state APIs.

Opportunity responses include `candidate_analysis`, `image_analysis`, and `lien_profile` summaries alongside existing history, title evidence, dealer correction, and alert workflows.

The app stores persisted run history in SQLite by default:

```text
DATABASE_URL=sqlite:///var/car-dealer.db
```

Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL when the MVP moves off local development. The SQLAlchemy models use portable JSON columns locally and PostgreSQL JSONB when running against PostgreSQL.

Production-grade Kijiji selectors and production deployment wiring are intentionally not implemented yet.

## Database Migrations

Run migrations against the configured `DATABASE_URL`:

```bash
uv run alembic upgrade head
```

For local SQLite, the default is:

```text
DATABASE_URL=sqlite:///var/car-dealer.db
```

For future PostgreSQL deployment, use a SQLAlchemy PostgreSQL URL:

```text
DATABASE_URL=postgresql+psycopg://user:password@localhost:55433/car_dealer
```

The current app still has a lightweight `init_db()` helper for local/test compatibility. Deployment should run Alembic migrations explicitly instead of relying on runtime table creation.

## Local PostgreSQL

SQLite remains the default for quick local development. To run the app against local PostgreSQL instead, use Docker Compose:

```bash
make postgres-up
make postgres-migrate
make api-postgres
```

The compose database uses:

```text
DATABASE_URL=postgresql+psycopg://car_dealer:car_dealer_password@localhost:55433/car_dealer
```

You can copy `.env.postgres.example` to a local env file when you want a Postgres-focused configuration. The file is an example only; `.env` remains ignored by git.

To verify migrations, service-layer persistence, and the FastAPI search route against PostgreSQL:

```bash
make postgres-verify
```

This starts Postgres, runs `alembic upgrade head`, executes the optional service-layer Postgres test, and executes the optional API route Postgres test with `TEST_DATABASE_URL` set. The tests reset the local compose database schema before and after they run.

To run only the API route verification:

```bash
make postgres-api-test
```

To stop the local database:

```bash
make postgres-down
```

## Combined Batch Ranking

The search pipeline can rank parsed Kijiji and AutoTrader search results together:

```bash
uv run python - <<'PY'
from app.services.search_pipeline import SearchPipeline
from app.scraping.contracts import SearchFilters
import asyncio

async def main():
    results = await SearchPipeline().run_multi_source_batch_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=5)
    )
    for item in results:
        print(item.listing.id, item.listing.vehicle.year, item.listing.vehicle.make, item.listing.vehicle.model, item.deal_score)

asyncio.run(main())
PY
```

In fixture mode, this uses saved HTML fixtures. In live mode, it fetches Kijiji and AutoTrader through Zyte, parses listing data, builds same-batch comparables, and returns ranked opportunities.

The pipeline now filters parsed search results by relevance to the requested year/make/model/query. For example, a search for `2020 Honda Civic Montreal` will filter unrelated Kia/Mazda/Volkswagen results before ranking. Borderline matches can be kept with a deal-score penalty; clearly off-query listings are removed from the scored opportunity list.

## Pre-Visit Candidate Enrichment

After combined ranking, use the pre-visit path to enrich only the shortlist:

```bash
uv run python - <<'PY'
from app.services.search_pipeline import SearchPipeline
from app.scraping.contracts import SearchFilters
import asyncio

async def main():
    results = await SearchPipeline().run_previsit_candidate_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25),
        max_candidates=50,
    )
    for item in results:
        print(
            item.listing.id,
            item.deal_score,
            len(item.listing.image_urls),
            item.listing.image_risk_reasons,
        )

asyncio.run(main())
PY
```

This stage fetches detail pages for the capped candidates, merges richer vehicle fields and image URLs, runs the image-risk gate, and re-scores the final shortlist. In live mode, Gemini image analysis is used only when explicitly enabled and configured; otherwise the deterministic analyzer keeps local runs reproducible.

## Saved Searches and Persisted Search Runs

The API run endpoint now persists the final pre-visit shortlist. For an ad-hoc dealer search, call:

```bash
curl -X POST http://127.0.0.1:8000/api/searches/run \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "AutoTrader Civic shortlist",
    "natural_language_query": "2020 Honda Civic Montreal",
    "structured_filters": {
      "make": "Honda",
      "model": "Civic",
      "year_min": 2020,
      "location_city": "Montreal",
      "location_province": "QC"
    },
    "listing_limit": 25,
    "sources": "both",
    "max_candidates": 50,
    "scheduled": true,
    "schedule_cron": "daily"
  }'
```

Use `sources` to choose `both`, `kijiji`, or `autotrader`. `max_candidates` is capped at 50 so detail-page fetching and image analysis only run on the final shortlist.

Preview natural-language interpretation before running search:

```bash
curl -X POST http://127.0.0.1:8000/api/searches/interpret \
  -H 'Content-Type: application/json' \
  -d '{
    "natural_language_query": "2020 Honda Civic under $20k under 100k km Montreal private seller",
    "structured_filters": {}
  }'
```

The response includes `interpreted_filters`, `applied_filters`, and interpretation confidence notes. Explicit structured filters override interpreted values. Search runs use the same interpretation path, so a natural-only query like `2020 Honda Civic Montreal` now runs with inferred make/model/year/location filters and returns `interpreted_filters` plus the applied `normalized_filters`.

To persist a reusable saved search, call:

```bash
curl -X POST http://127.0.0.1:8000/api/searches \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Daily Civic shortlist",
    "natural_language_query": "2020 Honda Civic Montreal",
    "structured_filters": {
      "make": "Honda",
      "model": "Civic",
      "year_min": 2020,
      "location_city": "Montreal",
      "location_province": "QC"
    },
    "listing_limit": 25,
    "sources": "both",
    "max_candidates": 50,
    "alerts_enabled": true,
    "in_app_alerts_enabled": true,
    "email_alerts_enabled": false
  }'
```

List and retrieve saved searches with:

```bash
curl http://127.0.0.1:8000/api/searches
curl http://127.0.0.1:8000/api/searches/{search_id}
```

Update a saved search schedule with:

```bash
curl -X PATCH http://127.0.0.1:8000/api/searches/{search_id} \
  -H 'Content-Type: application/json' \
  -d '{
    "scheduled": true,
    "schedule_cron": "every:6hours",
    "alerts_enabled": true,
    "in_app_alerts_enabled": true,
    "email_alerts_enabled": true
  }'
```

Supported schedule values are `daily`, `hourly`, `every:Nminutes`, `every:Nhours`, `every:Ndays`, `*/N * * * *`, `0 */N * * *`, and daily cron expressions like `0 8 * * *`. The scheduler treats these as intervals from `last_run_at`; scheduled searches that have never run are due immediately.

Run a saved search without a request body:

```bash
curl -X POST http://127.0.0.1:8000/api/searches/{search_id}/run
```

The saved-search run response includes a `run_id`, normalized filters, selected sources, per-source statuses, and ranked opportunities. The saved search `last_run_at` updates after a successful run.

Scheduled saved-search refresh can run as a one-shot cron job:

```bash
python -m app.cli.refresh_saved_searches
```

Or enable the optional in-process monitor:

```env
SAVED_SEARCH_REFRESH_ENABLED=true
SAVED_SEARCH_REFRESH_POLL_SECONDS=3600
SAVED_SEARCH_REFRESH_BATCH_LIMIT=25
SAVED_SEARCH_REFRESH_DEFAULT_SCHEDULE=daily
```

Saved-search alerts are generated after saved-search runs when `alerts_enabled` is true. High-score alerts use the dealer candidate score threshold, defaulting to 75. Price-drop alerts use persisted `listing_snapshots` for the same canonical listing URL and include old price, new price, drop amount, drop percent, and listing snapshot IDs in alert metadata. Older candidate rows without price history still fall back to candidate-snapshot comparison.

List alerts and mark an in-app alert read with:

```bash
curl http://127.0.0.1:8000/api/alerts
curl -X PATCH http://127.0.0.1:8000/api/alerts/{alert_id}/read
```

Email alerts are dry-run by default. Configure SMTP delivery with:

```env
ALERT_EMAIL_DRY_RUN=false
ALERT_EMAIL_FROM=alerts@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_USE_TLS=true
```

Retrieve run history and candidate details with:

```bash
curl http://127.0.0.1:8000/api/searches/runs
curl http://127.0.0.1:8000/api/searches/runs/{run_id}
curl http://127.0.0.1:8000/api/searches/runs/{run_id}/candidates/{candidate_id}
```

Each candidate snapshot stores the ranked vehicle fields, pricing summary, risk summary, relevance metadata, image URLs, and image-risk reasons generated before physical inspection. Search-run persistence also upserts the canonical `listings` row and appends a `listing_snapshots` observation for every candidate. The candidate `pricing_summary.price_history` object exposes current, previous, first, lowest, and highest prices plus `is_price_drop` when the latest listing snapshot is lower than the prior one. Each search run stores `source_statuses` entries for selected sources with `ok`, `empty`, or `failed` status, parsed listing counts, source URL, and failure reason/message when available.

Update candidate workflow state from the run detail screen with:

```bash
curl -X PATCH http://127.0.0.1:8000/api/searches/runs/{run_id}/candidates/{candidate_id} \
  -H 'Content-Type: application/json' \
  -d '{
    "selected": true,
    "hidden": false,
    "seller_contact_status": "contacted",
    "seller_notes": "Ask for VIN photo and service records."
  }'
```

Candidate snapshots now persist `selected`, `hidden`, `seller_contact_status`, and `seller_notes` so dealers can manage a shortlist before deeper analysis or report generation.

Promote a selected candidate to a durable opportunity with:

```bash
curl -X POST http://127.0.0.1:8000/api/searches/runs/{run_id}/candidates/{candidate_id}/promote
```

Promotion is idempotent. The first call creates an opportunity and stores `opportunity_id` on the candidate snapshot; later calls return the existing opportunity. List and retrieve promoted opportunities with:

```bash
curl http://127.0.0.1:8000/api/opportunities
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}
```

Update a promoted opportunity stage with:

```bash
curl -X PATCH http://127.0.0.1:8000/api/opportunities/{opportunity_id}/stage \
  -H 'Content-Type: application/json' \
  -d '{
    "stage": "contact_seller"
  }'
```

Supported stages are `new`, `candidate`, `needs_data`, `contact_seller`, `ready_to_visit`, `visited`, `offer_made`, `bought`, and `passed`. If key data is missing and the requested stage is `ready_to_visit`, the API keeps the opportunity at `needs_data` and returns `stage_update_warning: "missing_key_data_requires_override"`. To allow the transition anyway:

```bash
curl -X PATCH http://127.0.0.1:8000/api/opportunities/{opportunity_id}/stage \
  -H 'Content-Type: application/json' \
  -d '{
    "stage": "ready_to_visit",
    "override_missing_data_warning": true
  }'
```

Update opportunity seller follow-up context with:

```bash
curl -X PATCH http://127.0.0.1:8000/api/opportunities/{opportunity_id}/contact \
  -H 'Content-Type: application/json' \
  -d '{
    "seller_contact_status": "appointment_set",
    "seller_notes": "Seller can meet Saturday morning."
  }'
```

Track the pre-visit checklist with:

```bash
curl -X PATCH http://127.0.0.1:8000/api/opportunities/{opportunity_id}/visit-checklist \
  -H 'Content-Type: application/json' \
  -d '{
    "vin_confirmed": true,
    "service_records_requested": true,
    "lien_status_checked": false,
    "history_report_checked": false,
    "extra_photos_requested": true,
    "visit_appointment_set": false
  }'
```

Checklist fields are merged into the existing opportunity checklist. Updating stage, seller contact context, or checklist state marks the latest decision report `stale` if a report already exists.

Generate the first persisted decision report for a promoted opportunity with:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/reports
```

The report is versioned and stores a deterministic `report_json` summary built from the promoted opportunity, linked candidate snapshot, pricing summary, risk summary, image-risk notes, seller workflow state, visit checklist, and recommended next actions. Retrieve the latest report or open the printable HTML view with:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/reports/latest
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/reports/latest/html
```

Each generated report also writes PDF and CSV export artifacts to object storage and stores their object keys on the report row. Download the latest opportunity exports with:

```bash
curl -OJ http://127.0.0.1:8000/api/opportunities/{opportunity_id}/reports/latest/pdf
curl -OJ http://127.0.0.1:8000/api/opportunities/{opportunity_id}/reports/latest/csv
```

You can also fetch a report directly by ID:

```bash
curl http://127.0.0.1:8000/api/reports/{report_id}
curl -OJ http://127.0.0.1:8000/api/reports/{report_id}/pdf
curl -OJ http://127.0.0.1:8000/api/reports/{report_id}/csv
```

## Comparable Editing

Promoted opportunities store the scored comparable set used to estimate retail range and max-buy price. Dealers can remove bad comparables, recalculate pricing from the remaining included comparables, and generate a new report version.

List comparables for an opportunity:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/comparables
```

Remove a bad comparable:

```bash
curl -X PATCH http://127.0.0.1:8000/api/comparables/{comparable_id} \
  -H 'Content-Type: application/json' \
  -d '{
    "included": false,
    "excluded_reason": "Wrong trim and mileage band."
  }'
```

The response includes the updated comparable set, a new `pricing_analysis`, and a newly generated decision `report`. At least one comparable must remain included. Recalculated pricing updates the promoted candidate pricing summary, including `retail_low_cad`, `retail_mid_cad`, `retail_high_cad`, `max_buy_price_cad`, `starting_offer_cad`, and `comparable_count`.

You can also recalculate without changing inclusion state:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/recalculate
```

Decision reports include the comparable set under `comparables` and `evidence.comparables`, render a Comparables section in HTML, and show the comparable count in the Pricing section.

Capture dealer pilot feedback after a report is reviewed with:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/feedback \
  -H 'Content-Type: application/json' \
  -d '{
    "usefulness_rating": 4,
    "accuracy_rating": 3,
    "dealer_decision": "pursue",
    "missing_info": ["lien status", "service records"],
    "incorrect_info": ["trim uncertainty"],
    "notes": "Good enough to call the seller."
  }'
```

Feedback is linked to the latest decision report version when one exists. Review per-opportunity entries, the global feedback feed, and the pilot summary with:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/feedback
curl http://127.0.0.1:8000/api/feedback
curl http://127.0.0.1:8000/api/feedback/summary
```

For a single listing URL, use the same endpoint with `listing_url`:

```bash
curl -X POST http://127.0.0.1:8000/api/searches/run \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Single Kijiji listing",
    "listing_url": "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
    "vin": "2HGFC2F59LH000001",
    "sources": "both",
    "listing_limit": 25
  }'
```

The single-listing path detects Kijiji or AutoTrader from the URL, fetches the detail page, parses the target vehicle, builds comparable filters from the parsed year/make/model/location, searches comparable listings from the selected sources, scores the target, runs image-risk analysis on the target, and persists one ranked candidate. VIN can be attached when a listing URL is present.

To run VIN-only analysis without a listing URL:

```bash
curl -X POST http://127.0.0.1:8000/api/searches/run \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "VIN-only Civic check",
    "vin": "2HGFC2F59LH000001",
    "structured_filters": {
      "model": "Civic",
      "location_city": "Montreal",
      "location_province": "QC"
    },
    "sources": "both",
    "listing_limit": 25
  }'
```

VIN-only analysis validates the VIN check digit, decodes basic local identity fields such as model year and known WMI make/country, searches selected listing sources for comparables/source matches, and returns a preliminary candidate with explicit source statuses for unresolved history, lien/title, and recall checks.

To analyze one listing and immediately promote it into the opportunity workflow:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/from-listing \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Direct listing intake",
    "listing_url": "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
    "vin": "2HGFC2F59LH000001",
    "sources": "both",
    "listing_limit": 25
  }'
```

The response includes the persisted `run_id`, promoted `candidate_id`, and `opportunity`. When a VIN is attached, the promoted opportunity checklist starts with `vin_confirmed: true`. Generated decision reports include `evidence.intake_mode: "single_listing"` and the source listing URL.

To analyze a VIN and immediately promote it into the opportunity workflow:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/from-vin \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Direct VIN intake",
    "vin": "2HGFC2F59LH000001",
    "model": "Civic",
    "sources": "both",
    "listing_limit": 25
  }'
```

Generated VIN reports include `evidence.intake_mode: "vin"` and a `verification` section. Until paid integrations or document uploads are added, lien/title status is marked unverified and recall status is marked not checked. Manual evidence or uploaded documents can then move those checks into reviewed, blocked, or verified states.

To ingest a CARFAX Canada-derived or manually reviewed vehicle history report for an opportunity:

```bash
curl -X PUT http://127.0.0.1:8000/api/opportunities/{opportunity_id}/history \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "carfax",
    "source_name": "CARFAX Canada",
    "report_identifier": "CFX-123",
    "title_brand": "clean",
    "accident_claims": [
      {
        "date": "2022-04-12",
        "amount_cad": 1400,
        "description": "Rear bumper claim",
        "severity": "minor"
      }
    ],
    "registration_events": [
      {
        "date": "2020-05-10",
        "province": "QC",
        "event": "registered"
      }
    ],
    "owners_count": 2,
    "odometer_records": [
      {
        "date": "2024-11-01",
        "mileage_km": 78200,
        "source": "service"
      }
    ],
    "odometer_issue": false,
    "service_records_count": 8,
    "service_records": [
      {
        "date": "2024-11-01",
        "mileage_km": 78200,
        "description": "Oil service"
      }
    ],
    "import_history": [],
    "salvage_status": "clear",
    "flood_status": "clear",
    "fire_status": "clear",
    "theft_status": "clear",
    "summary": "Minor claim only; regular service records present.",
    "raw_payload": {}
  }'
```

History ingestion clears only the `vehicle_history` missing-data item, marks `history_report_checked` complete, and marks the latest decision report stale. It does not clear lien/title verification or recall checks. New decision reports include a `history_profile` section and set `verification.history.status` to `provided`.

## Dealer Corrections and Explicit Overrides

Promoted opportunities can store dealer corrections without mutating the original scraped candidate snapshot. Use corrections when a dealer confirms a bad parsed field or an explicit verification status before regenerating a decision report.

Create a correction:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/corrections \
  -H 'Content-Type: application/json' \
  -d '{
    "entity_type": "vehicle",
    "field_name": "mileage_km",
    "new_value": 43210,
    "reason": "Odometer photo received."
  }'
```

List correction history:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/corrections
```

Supported correction fields are `vehicle.year`, `vehicle.make`, `vehicle.model`, `vehicle.trim`, `vehicle.vin`, `vehicle.mileage_km`, `listing.asking_price_cad`, `history.accident_history_status`, and `title.lien_status`.

Supported accident history values are `unknown`, `none_reported`, `accident_reported`, `minor_damage`, `moderate_damage`, and `major_damage`. Supported lien/title values are `unknown`, `needs_review`, `clear`, `lien_found`, `payout_pending`, `payout_ready`, `payout_paid`, `released`, and `blocked`.

Saving a correction records the old and new values, marks the latest decision report `stale`, and exposes active corrections in the opportunity payload under `dealer_corrections`. Future decision reports apply the latest active correction per field under `evidence.dealer_corrections`. Vehicle and listing corrections overlay report facts. `history.accident_history_status` marks history as dealer-corrected and clears `vehicle_history`; `title.lien_status` clears `lien_verification` only when the corrected status is `clear` or `released`.

## Document Upload Fallback

Promoted opportunities can store fallback evidence files when structured integrations are unavailable.

Supported document types:

- `carfax_pdf`
- `uvip`
- `seller_document`
- `mechanic_quote`
- `auction_condition_report`
- `service_invoice`
- `ownership_document`
- `ppsa_report`
- `ppsr_report`
- `lien_release`
- `lender_payout_statement`
- `transport_canada_recall_report`
- `oem_recall_report`
- `recall_completion_receipt`
- `import_compliance_document`
- `riv_inspection`
- `statement_of_compliance`
- `cbb_valuation`
- `manheim_mmr`
- `openlane_auction_report`
- `adesa_auction_report`
- `traderev_bid_report`
- `trade_in_appraisal`
- `wholesale_invoice`

Upload a PDF, image, or text attachment:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/documents \
  -F document_type=carfax_pdf \
  -F notes="Seller supplied report" \
  -F file=@/path/to/carfax.pdf
```

List and download stored evidence:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/documents
curl -OJ http://127.0.0.1:8000/api/opportunities/{opportunity_id}/documents/{document_id}/download
```

Files are stored in the configured object store root under `opportunities/{opportunity_id}/documents/`. `DOCUMENT_UPLOAD_MAX_BYTES` controls the upload size cap and defaults to 20 MB. Uploading CARFAX evidence marks history checked and clears `vehicle_history`. Lien/title uploads create linked title evidence: UVIP, PPSA/PPSR, and ownership documents start as `needs_review`, lender payout statements start as `payout_pending`, and lien release documents start as `released`. Recall/compliance uploads create linked recall evidence: Transport Canada and OEM recall reports start as `needs_review`, recall completion receipts start as `completed`, and import/RIV/SOC documents create import compliance evidence for review. Wholesale uploads create linked wholesale evidence for CBB, Manheim MMR, OPENLANE/ADESA/TradeRev, trade-in appraisals, wholesale invoices, and auction condition reports. Decision reports include uploaded files under `evidence.uploaded_documents` and render an Uploaded Evidence section.

## Lien and Title Evidence

Use title evidence records to capture manual lien checks, PPSA/PPSR lookup references, UVIP review, lender payout status, seller ownership verification, and final title clearance.

Create manual title evidence:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/title-evidence \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "ppsa_lookup",
    "title_clearance_status": "clear",
    "provider": "Manual PPSA portal",
    "lookup_reference": "PPSA-123",
    "checked_at": "2026-06-14",
    "seller_name": "Jane Seller",
    "registered_owner_name": "Jane Seller",
    "ownership_verified": true,
    "payout_required": false,
    "payout_status": "not_required",
    "notes": "No active security interest found."
  }'
```

List title evidence:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/title-evidence
```

Supported `source_type` values are `manual`, `uvip`, `ppsa_lookup`, `ppsr_lookup`, `seller_ownership`, `lender_payout`, `lien_release`, and `document_upload`. Supported `title_clearance_status` values are `unknown`, `needs_review`, `clear`, `lien_found`, `payout_pending`, `payout_ready`, `payout_paid`, `released`, and `blocked`.

Only `clear` and `released` clear the `lien_verification` missing-data item and mark `lien_status_checked` complete. `lien_found`, payout states, `needs_review`, and `blocked` keep the opportunity blocked from clean ready-to-visit/title clearance unless explicitly overridden. Decision reports include `title_evidence`, set `verification.lien_title` from the latest title evidence, and render a Title and Lien Evidence section.

## Recall and Canadian Import Compliance

Use recall/compliance evidence records to capture Transport Canada recall database checks, OEM portal lookups, dealer recall completion receipts, RIV/import compliance evidence, and seller-provided recall clearance documents. Transport Canada directs users to search recalls by VIN/manufacturer and Canadian import guidance requires imported vehicles to be clear of recalls and complete RIV inspection/compliance steps when applicable.

Create manual recall/compliance evidence:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/recall-compliance \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "transport_canada",
    "recall_status": "no_open_recalls",
    "compliance_status": "compliant",
    "provider": "Transport Canada recalls database",
    "lookup_reference": "TC-LOOKUP-123",
    "checked_at": "2026-06-14",
    "remedy_status": "not_required",
    "import_country": "United States",
    "import_form": "RIV Form 1",
    "riv_case_number": "RIV-123",
    "inspection_required": false,
    "notes": "No open recall found and import compliance evidence reviewed."
  }'
```

List recall/compliance evidence:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/recall-compliance
```

Supported `source_type` values are `manual`, `transport_canada`, `oem_portal`, `dealer_service`, `import_compliance`, `riv`, and `document_upload`. Supported `recall_status` values are `unknown`, `not_checked`, `no_open_recalls`, `open_recall`, `incomplete`, `completed`, and `needs_review`. Supported `compliance_status` values are `unknown`, `not_applicable`, `needs_review`, `compliant`, `non_compliant`, `needs_inspection`, `import_pending`, and `blocked`. Supported `remedy_status` values are `unknown`, `not_required`, `required`, `scheduled`, `completed`, and `parts_unavailable`.

`no_open_recalls` or `completed` plus `not_applicable` or `compliant` clears the `recall_compliance` missing-data item. Open recalls, incomplete recalls, needs-review evidence, remedy-required states, non-compliance, RIV inspection needs, import-pending state, and blocked import state keep `recall_compliance` in missing key data. Decision reports include `recall_compliance`, set `verification.recall` from the latest evidence, add recall/import risk factors, and render a Recall and Compliance section.

## Wholesale and Trade-In Evidence

Use wholesale evidence records to capture Canadian Black Book, Manheim MMR, OPENLANE/ADESA/TradeRev auction reports, trade-in appraisals, condition grade, bid activity, auction sale range, and a wholesale-supported buy calculation. This workflow is manual/document-backed so it can be used with exported reports or screenshots from authenticated valuation/auction tools.

Create manual wholesale evidence:

```bash
curl -X POST http://127.0.0.1:8000/api/opportunities/{opportunity_id}/wholesale-evidence \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "canadian_black_book",
    "provider": "Canadian Black Book",
    "lookup_reference": "CBB-123",
    "region": "QC",
    "wholesale_low_cad": 19500,
    "wholesale_avg_cad": 21000,
    "wholesale_high_cad": 22500,
    "trade_in_value_cad": 20500,
    "retail_value_cad": 24800,
    "condition_grade": "clean",
    "buyer_fee_cad": 500,
    "transport_estimate_cad": 300,
    "reconditioning_estimate_cad": 900,
    "notes": "CBB wholesale average reviewed."
  }'
```

List wholesale evidence:

```bash
curl http://127.0.0.1:8000/api/opportunities/{opportunity_id}/wholesale-evidence
```

Supported `source_type` values are `manual`, `canadian_black_book`, `manheim_mmr`, `openlane`, `adesa`, `traderev`, `auction_report`, `trade_in_appraisal`, and `document_upload`. Supported `condition_grade` values are `unknown`, `rough`, `average`, `clean`, `extra_clean`, and `auction_1` through `auction_5`.

The support calculation uses the latest evidence. It picks a representative wholesale value from wholesale average, trade-in value, auction sale average, high bid, or sale price, applies a condition adjustment, then subtracts buyer fee, transport, and reconditioning estimates. The report exposes `wholesale_supported_max_buy_cad` and `wholesale_suggested_opening_bid_cad`. If the retail-derived max buy exceeds wholesale support, or if auction bid activity/condition is weak, the decision report adds risk factors and renders a Wholesale and Trade-In Evidence section.

## Real URL Pilot Smoke

Before asking a dealer to test the dashboard, run the pasted-listing workflow against the API with real marketplace URLs. The smoke runner checks source readiness, submits each URL to direct opportunity intake, generates a decision report, and writes a JSON artifact with source diagnostics and failures.

Run a local fixture sanity check against a fixture-mode API:

```bash
uv run python -m app.cli.pilot_smoke \
  --base-url http://127.0.0.1:8002 \
  --allow-fixture \
  --submit-smoke-feedback \
  "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001"
```

Run the real pilot smoke after configuring live URL intake:

```bash
APP_MODE=pilot SCRAPING_FIXTURE_MODE=false SCRAPING_USE_ZYTE=true ZYTE_API_KEY=... \
uv run python -m app.cli.pilot_smoke \
  --base-url http://127.0.0.1:8000 \
  "https://www.kijiji.ca/..." \
  "https://www.autotrader.ca/..."
```

You can also pass `--url-file var/pilot-smoke/urls.txt`; blank lines and `#` comments are ignored, and each line may be `URL|VIN` when a VIN is available. By default the command requires `/api/settings/source-health` to report `live_url_intake_enabled: true`; use `--allow-fixture` only for local fixture checks.

The default artifact path is:

```text
var/pilot-smoke/latest.json
```

## Scraping Smoke Commands

### Kijiji

Run safely against local fixtures:

```bash
uv run python -m app.cli.scrape_kijiji "2020 Honda Civic Montreal" --fixture-mode
```

Run live through Zyte after configuring `.env`:

```bash
uv run python -m app.cli.scrape_kijiji "2020 Honda Civic Montreal"
```

Fetch the first listing from the search results as well:

```bash
uv run python -m app.cli.scrape_kijiji "2020 Honda Civic Montreal" --fetch-first-listing
```

Save live HTML into parser fixtures:

```bash
uv run python -m app.cli.scrape_kijiji \
  "2020 Honda Civic Montreal" \
  --save-search-fixture fixtures/html/kijiji/search_results_live.html \
  --fetch-first-listing \
  --save-listing-fixture fixtures/html/kijiji/listing_detail_live.html
```

The command saves raw snapshots through the local object store. By default, object data is written under `var/object-store`, which is ignored by git.

### AutoTrader

Run safely against local fixtures:

```bash
uv run python -m app.cli.scrape_autotrader "2020 Honda Civic Montreal" --fixture-mode
```

Run live through Zyte after configuring `.env`:

```bash
uv run python -m app.cli.scrape_autotrader "2020 Honda Civic Montreal" --limit 20
```

Save live AutoTrader HTML into parser fixtures:

```bash
uv run python -m app.cli.scrape_autotrader \
  "2020 Honda Civic Montreal" \
  --limit 20 \
  --save-search-fixture fixtures/html/autotrader/search_results_live.html \
  --fetch-first-listing \
  --save-listing-fixture fixtures/html/autotrader/listing_detail_live.html
```
