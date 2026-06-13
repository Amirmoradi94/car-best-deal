# Technical Architecture and Database Schema

## 1. Purpose

This document defines the technical architecture for the MVP described in `mvp-product-requirements.md`.

The first implementation milestone is:

- Data model.
- Scoring engine.
- Preliminary max-buy-price calculator.
- Missing-data penalties.

The app must support a discovery-first workflow for an independent used-car dealer in Quebec, starting with search criteria and producing ranked opportunities from AutoTrader Canada and Kijiji.

## 2. Recommended MVP Stack

Backend:

- Python 3.12+.
- FastAPI.
- Pydantic for request/response schemas and AI output validation.
- SQLAlchemy 2.x.
- Alembic migrations.
- PostgreSQL.
- Redis for queues, locks, cache, and rate limits.
- RQ, Celery, or Dramatiq for async jobs.

Scraping:

- Zyte API client.
- Scrapling-based parser adapters.
- Per-source adapter modules.

AI:

- Gemini Flash through a configurable model adapter.
- Strict JSON schemas for all AI outputs.
- Model name, prompt version, and response metadata stored per AI run.

Storage:

- PostgreSQL for canonical structured data.
- Object storage for raw HTML, screenshots, source images, PDFs, and exported reports.
- Raw source snapshot retention: 90 days.

Frontend:

- Dealer dashboard web app.
- Ranked opportunities as the default landing view.
- Report pages for full analysis.

## 3. High-Level Architecture

```text
Dealer Web App
      |
      v
FastAPI Backend
      |
      +--> PostgreSQL
      +--> Redis / Job Queue
      +--> Object Storage
      |
      +--> Scraping Workers
      |       +--> Zyte API
      |       +--> Scrapling Parsers
      |
      +--> AI Workers
      |       +--> Gemini Model Adapter
      |
      +--> Scoring Workers
              +--> Comparable Engine
              +--> Risk Engine
              +--> Pricing Engine
```

## 4. Main Backend Modules

Suggested package layout:

```text
app/
  api/
    routes/
      searches.py
      opportunities.py
      reports.py
      settings.py
      uploads.py
      alerts.py
  core/
    config.py
    security.py
    logging.py
    time.py
  db/
    base.py
    session.py
    models/
    migrations/
  schemas/
    api/
    ai/
    domain/
  services/
    searches/
    opportunities/
    pricing/
    scoring/
    reports/
    alerts/
    uploads/
  integrations/
    zyte/
    gemini/
    object_storage/
    email/
  scraping/
    adapters/
      autotrader.py
      kijiji.py
    parsers/
    normalization/
  workers/
    jobs.py
    queues.py
  tests/
```

## 5. Domain Concepts

### DealerAccount

Single dealership/user account in MVP.

### Search

Saved search definition, including structured filters, natural-language input, location, radius, schedule, alert rules, and dealer scoring settings.

### SearchRun

One execution of a saved or ad hoc search.

### Listing

Canonical listing identity across sources. A listing may have many snapshots over time.

### ListingSnapshot

Raw observation of a listing at a point in time, including extracted fields and links to raw stored artifacts.

### VehicleProfile

Canonical vehicle identity assembled from listing data, VIN decode, user corrections, and uploaded documents.

### ComparableListing

Listing used as a comparable for a target opportunity.

### Opportunity

A vehicle/listing that appears in the dealer workflow and has a stage such as New, Candidate, Ready to Visit, Bought, or Passed.

### CandidateAnalysis

Deep analysis for selected candidates, including images, risk, price, and report generation.

### DecisionReport

Versioned output report with recommendation, pricing, risks, confidence, and evidence.

## 6. Core Enums

Use database enums or constrained strings. Prefer constrained strings if easier to evolve early.

### search_run_status

```text
queued
running
completed
completed_partial
failed
cancelled
```

### opportunity_stage

```text
new
candidate
needs_data
contact_seller
ready_to_visit
visited
offer_made
bought
passed
```

### report_status

```text
preliminary
partial
full
stale
failed
```

### seller_type

```text
private
dealer
auction
unknown
```

### source_name

```text
autotrader
kijiji
manual
upload
carfax
quebec_lien
other
```

### confidence_level

```text
low
medium
high
unknown
```

### recommendation

```text
buy
buy_only_cheap
pass
needs_more_data
```

## 7. Database Schema

All tables should include:

- `id` as UUID primary key.
- `created_at`.
- `updated_at`.

Use `numeric(12,2)` for money fields. Store currency explicitly where external data may vary, but default MVP currency is CAD.

### 7.1 dealer_accounts

Stores the single-user dealership account.

```sql
create table dealer_accounts (
  id uuid primary key,
  email text not null unique,
  display_name text,
  dealership_name text,
  timezone text not null default 'America/Toronto',
  default_city text default 'Montreal',
  default_province text default 'QC',
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

### 7.2 dealer_settings

Stores configurable dealer preferences.

```sql
create table dealer_settings (
  id uuid primary key,
  dealer_account_id uuid not null references dealer_accounts(id),
  default_target_profit_cad numeric(12,2) not null default 2500,
  risk_tolerance text not null default 'medium',
  preferred_brands jsonb not null default '[]',
  preferred_models jsonb not null default '[]',
  default_search_radius_km integer not null default 50,
  include_overpriced_default boolean not null default false,
  candidate_score_threshold numeric(5,2) not null default 75,
  max_candidate_count integer not null default 50,
  max_images_per_candidate integer not null default 10,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (dealer_account_id)
);
```

### 7.3 searches

Saved or one-time search definition.

```sql
create table searches (
  id uuid primary key,
  dealer_account_id uuid not null references dealer_accounts(id),
  name text not null,
  mode text not null default 'structured',
  natural_language_query text,
  structured_filters jsonb not null default '{}',
  location_city text,
  location_province text not null default 'QC',
  radius_km integer not null default 50,
  listing_limit integer not null default 25,
  include_overpriced boolean not null default false,
  target_profit_cad numeric(12,2),
  risk_tolerance text,
  scheduled boolean not null default false,
  schedule_cron text,
  alerts_enabled boolean not null default false,
  email_alerts_enabled boolean not null default false,
  in_app_alerts_enabled boolean not null default true,
  last_run_at timestamptz,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_searches_dealer on searches(dealer_account_id);
create index idx_searches_scheduled on searches(scheduled, last_run_at);
```

### 7.4 search_runs

One execution of a search.

```sql
create table search_runs (
  id uuid primary key,
  search_id uuid references searches(id),
  dealer_account_id uuid not null references dealer_accounts(id),
  status text not null default 'queued',
  requested_listing_limit integer not null default 25,
  started_at timestamptz,
  completed_at timestamptz,
  total_listings_found integer not null default 0,
  total_listings_normalized integer not null default 0,
  total_opportunities_created integer not null default 0,
  error_summary text,
  source_failures jsonb not null default '[]',
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_search_runs_search on search_runs(search_id);
create index idx_search_runs_dealer_status on search_runs(dealer_account_id, status);
```

### 7.5 source_snapshots

Stores references to raw source artifacts.

```sql
create table source_snapshots (
  id uuid primary key,
  dealer_account_id uuid not null references dealer_accounts(id),
  source_name text not null,
  source_url text,
  artifact_type text not null,
  object_key text not null,
  content_hash text,
  http_status integer,
  fetched_at timestamptz not null,
  expires_at timestamptz not null,
  metadata jsonb not null default '{}',
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_source_snapshots_expires on source_snapshots(expires_at);
create index idx_source_snapshots_hash on source_snapshots(content_hash);
```

### 7.6 listings

Canonical listing record.

```sql
create table listings (
  id uuid primary key,
  source_name text not null,
  source_listing_id text,
  canonical_url text not null,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  active boolean not null default true,
  dedupe_key text,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (source_name, canonical_url)
);
```

Indexes:

```sql
create index idx_listings_source_listing_id on listings(source_name, source_listing_id);
create index idx_listings_dedupe_key on listings(dedupe_key);
create index idx_listings_active_last_seen on listings(active, last_seen_at);
```

### 7.7 listing_snapshots

Extracted listing data for one observation.

```sql
create table listing_snapshots (
  id uuid primary key,
  listing_id uuid not null references listings(id),
  search_run_id uuid references search_runs(id),
  source_snapshot_id uuid references source_snapshots(id),
  source_name text not null,
  observed_at timestamptz not null,
  title text,
  description text,
  asking_price_cad numeric(12,2),
  mileage_km integer,
  location_city text,
  location_province text,
  seller_type text not null default 'unknown',
  seller_name text,
  vin text,
  year integer,
  make text,
  model text,
  trim text,
  body_style text,
  drivetrain text,
  transmission text,
  engine text,
  exterior_color text,
  interior_color text,
  certified boolean,
  as_is boolean,
  accident_status_claim text,
  extraction_method text not null,
  extraction_confidence numeric(5,4),
  extracted_fields jsonb not null default '{}',
  source_evidence jsonb not null default '{}',
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_listing_snapshots_listing_observed on listing_snapshots(listing_id, observed_at desc);
create index idx_listing_snapshots_search_run on listing_snapshots(search_run_id);
create index idx_listing_snapshots_vehicle_lookup on listing_snapshots(make, model, year, trim);
create index idx_listing_snapshots_price on listing_snapshots(asking_price_cad);
create index idx_listing_snapshots_vin on listing_snapshots(vin);
```

### 7.8 listing_images

Images discovered for a listing.

```sql
create table listing_images (
  id uuid primary key,
  listing_snapshot_id uuid not null references listing_snapshots(id),
  source_url text,
  source_snapshot_id uuid references source_snapshots(id),
  object_key text,
  position integer not null,
  width integer,
  height integer,
  content_hash text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_listing_images_snapshot_position on listing_images(listing_snapshot_id, position);
```

### 7.9 vehicle_profiles

Canonical vehicle profile for an opportunity or direct analysis.

```sql
create table vehicle_profiles (
  id uuid primary key,
  vin text,
  year integer,
  make text,
  model text,
  trim text,
  body_style text,
  engine text,
  transmission text,
  drivetrain text,
  mileage_km integer,
  exterior_color text,
  interior_color text,
  canonical_confidence numeric(5,4),
  identity_status text not null default 'partial',
  field_sources jsonb not null default '{}',
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_vehicle_profiles_vin on vehicle_profiles(vin);
create index idx_vehicle_profiles_lookup on vehicle_profiles(make, model, year, trim);
```

### 7.10 opportunities

Dealer workflow item.

```sql
create table opportunities (
  id uuid primary key,
  dealer_account_id uuid not null references dealer_accounts(id),
  search_run_id uuid references search_runs(id),
  listing_id uuid references listings(id),
  latest_listing_snapshot_id uuid references listing_snapshots(id),
  vehicle_profile_id uuid references vehicle_profiles(id),
  stage text not null default 'new',
  deal_score numeric(5,2),
  preliminary boolean not null default true,
  missing_key_data jsonb not null default '[]',
  source_failure_notes jsonb not null default '[]',
  is_overpriced boolean not null default false,
  candidate_selected boolean not null default false,
  candidate_selected_reason text,
  seller_contact_status text,
  seller_notes text,
  last_price_cad numeric(12,2),
  last_price_seen_at timestamptz,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_opportunities_dealer_stage on opportunities(dealer_account_id, stage);
create index idx_opportunities_dealer_score on opportunities(dealer_account_id, deal_score desc);
create index idx_opportunities_search_run on opportunities(search_run_id);
create index idx_opportunities_listing on opportunities(listing_id);
```

### 7.11 comparable_listings

Comparable listing candidate for an opportunity.

```sql
create table comparable_listings (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  listing_id uuid references listings(id),
  listing_snapshot_id uuid references listing_snapshots(id),
  source_name text not null,
  source_url text,
  year integer,
  make text,
  model text,
  trim text,
  mileage_km integer,
  asking_price_cad numeric(12,2),
  location_city text,
  location_province text,
  seller_type text,
  accident_status text,
  similarity_score numeric(5,4) not null,
  included boolean not null default true,
  excluded_reason text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_comparables_opportunity_included on comparable_listings(opportunity_id, included);
create index idx_comparables_similarity on comparable_listings(opportunity_id, similarity_score desc);
```

### 7.12 pricing_analyses

Versioned pricing output.

```sql
create table pricing_analyses (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  version integer not null,
  status text not null default 'preliminary',
  comparable_count integer not null default 0,
  retail_low_cad numeric(12,2),
  retail_mid_cad numeric(12,2),
  retail_high_cad numeric(12,2),
  estimated_reconditioning_cad numeric(12,2) not null default 0,
  selling_costs_cad numeric(12,2) not null default 0,
  transport_cost_cad numeric(12,2) not null default 0,
  buying_fees_cad numeric(12,2) not null default 0,
  capital_cost_cad numeric(12,2) not null default 0,
  risk_reserve_cad numeric(12,2) not null default 0,
  target_profit_cad numeric(12,2) not null,
  max_buy_price_cad numeric(12,2),
  starting_offer_cad numeric(12,2),
  calculation_inputs jsonb not null default '{}',
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (opportunity_id, version)
);
```

Indexes:

```sql
create index idx_pricing_opportunity_version on pricing_analyses(opportunity_id, version desc);
```

### 7.13 risk_analyses

Versioned risk output.

```sql
create table risk_analyses (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  version integer not null,
  risk_score numeric(5,2),
  risk_level text not null default 'unknown',
  recommendation_modifier text,
  risk_factors jsonb not null default '[]',
  missing_verifications jsonb not null default '[]',
  deterministic_rules_applied jsonb not null default '[]',
  ai_risk_summary text,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (opportunity_id, version)
);
```

### 7.14 history_profiles

History facts from paid/API source, manual entry, or upload.

```sql
create table history_profiles (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  source_type text not null,
  source_snapshot_id uuid references source_snapshots(id),
  title_brand text not null default 'unknown',
  accident_claims jsonb not null default '[]',
  owners_count integer,
  service_record_count integer,
  odometer_issue boolean,
  registration_provinces jsonb not null default '[]',
  import_history jsonb not null default '{}',
  verified boolean not null default false,
  confidence numeric(5,4),
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

### 7.15 lien_profiles

Lien/title evidence for Quebec MVP.

```sql
create table lien_profiles (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  source_type text not null,
  source_snapshot_id uuid references source_snapshots(id),
  lien_status text not null default 'not_verified',
  title_status text not null default 'unknown',
  evidence_summary text,
  verified boolean not null default false,
  confidence numeric(5,4),
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

### 7.16 candidate_analyses

Tracks deeper analysis for final candidates.

```sql
create table candidate_analyses (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  status text not null default 'queued',
  selected_reason text,
  score_at_selection numeric(5,2),
  max_images_to_analyze integer not null default 10,
  images_discovered_count integer not null default 0,
  images_analyzed_count integer not null default 0,
  started_at timestamptz,
  completed_at timestamptz,
  error_summary text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_candidate_analyses_opportunity on candidate_analyses(opportunity_id);
create index idx_candidate_analyses_status on candidate_analyses(status);
```

### 7.17 image_analyses

AI findings for candidate listing images.

```sql
create table image_analyses (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  listing_image_id uuid references listing_images(id),
  model_provider text not null,
  model_name text not null,
  prompt_version text not null,
  findings jsonb not null default '[]',
  visible_damage boolean,
  rust_detected boolean,
  panel_mismatch_detected boolean,
  tire_wear_concern boolean,
  interior_condition text,
  warning_lights_visible boolean,
  odometer_visible boolean,
  odometer_km integer,
  vin_visible boolean,
  vin text,
  risk_adjustment numeric(5,2) not null default 0,
  confidence numeric(5,4),
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_image_analyses_opportunity on image_analyses(opportunity_id);
```

### 7.18 decision_reports

Versioned report output.

```sql
create table decision_reports (
  id uuid primary key,
  opportunity_id uuid not null references opportunities(id),
  version integer not null,
  status text not null,
  recommendation text not null,
  pricing_analysis_id uuid references pricing_analyses(id),
  risk_analysis_id uuid references risk_analyses(id),
  report_json jsonb not null,
  confidence_by_section jsonb not null default '{}',
  pdf_object_key text,
  csv_object_key text,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (opportunity_id, version)
);
```

### 7.19 dealer_corrections

Explicit overrides from the dealer.

```sql
create table dealer_corrections (
  id uuid primary key,
  dealer_account_id uuid not null references dealer_accounts(id),
  opportunity_id uuid references opportunities(id),
  entity_type text not null,
  entity_id uuid,
  field_name text not null,
  old_value jsonb,
  new_value jsonb not null,
  reason text,
  apply_to_future boolean not null default true,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_dealer_corrections_dealer_field on dealer_corrections(dealer_account_id, entity_type, field_name);
```

### 7.20 ai_runs

Audit log for AI calls.

```sql
create table ai_runs (
  id uuid primary key,
  dealer_account_id uuid references dealer_accounts(id),
  opportunity_id uuid references opportunities(id),
  task_type text not null,
  model_provider text not null,
  model_name text not null,
  prompt_version text not null,
  input_object_key text,
  output_json jsonb,
  schema_valid boolean not null default false,
  confidence numeric(5,4),
  token_usage jsonb not null default '{}',
  cost_estimate_usd numeric(12,6),
  error text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

### 7.21 alerts

In-app and email alert events.

```sql
create table alerts (
  id uuid primary key,
  dealer_account_id uuid not null references dealer_accounts(id),
  search_id uuid references searches(id),
  opportunity_id uuid references opportunities(id),
  alert_type text not null,
  title text not null,
  body text not null,
  channel text not null,
  status text not null default 'pending',
  sent_at timestamptz,
  read_at timestamptz,
  metadata jsonb not null default '{}',
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

Indexes:

```sql
create index idx_alerts_dealer_status on alerts(dealer_account_id, status);
create index idx_alerts_opportunity on alerts(opportunity_id);
```

## 8. Relationships

```text
dealer_accounts 1 -> 1 dealer_settings
dealer_accounts 1 -> many searches
searches 1 -> many search_runs
search_runs 1 -> many listing_snapshots
listings 1 -> many listing_snapshots
listing_snapshots 1 -> many listing_images
dealer_accounts 1 -> many opportunities
opportunities many -> 1 listings
opportunities many -> 1 vehicle_profiles
opportunities 1 -> many comparable_listings
opportunities 1 -> many pricing_analyses
opportunities 1 -> many risk_analyses
opportunities 1 -> many candidate_analyses
opportunities 1 -> many image_analyses
opportunities 1 -> many decision_reports
opportunities 1 -> many dealer_corrections
dealer_accounts 1 -> many alerts
```

## 9. API Endpoints

### Settings

```text
GET    /api/settings
PATCH  /api/settings
```

### Searches

```text
POST   /api/searches
GET    /api/searches
GET    /api/searches/{search_id}
PATCH  /api/searches/{search_id}
POST   /api/searches/{search_id}/run
GET    /api/search-runs/{search_run_id}
```

### Opportunities

```text
GET    /api/opportunities
GET    /api/opportunities/{opportunity_id}
PATCH  /api/opportunities/{opportunity_id}/stage
PATCH  /api/opportunities/{opportunity_id}/contact
POST   /api/opportunities/{opportunity_id}/select-candidate
POST   /api/opportunities/{opportunity_id}/remove-candidate
POST   /api/opportunities/{opportunity_id}/analyze
```

### Comparables

```text
GET    /api/opportunities/{opportunity_id}/comparables
PATCH  /api/comparables/{comparable_id}
POST   /api/opportunities/{opportunity_id}/recalculate
```

### Reports

```text
GET    /api/opportunities/{opportunity_id}/reports/latest
GET    /api/reports/{report_id}
POST   /api/opportunities/{opportunity_id}/reports
GET    /api/reports/{report_id}/export.pdf
GET    /api/reports/{report_id}/export.csv
```

### Uploads

```text
POST   /api/opportunities/{opportunity_id}/uploads/history
POST   /api/opportunities/{opportunity_id}/uploads/lien
```

### Direct Analysis

```text
POST   /api/analyze/listing-url
POST   /api/analyze/vin
```

### Alerts

```text
GET    /api/alerts
PATCH  /api/alerts/{alert_id}/read
```

## 10. Job Queue Design

Use separate queues so source failures and expensive jobs do not block quick tasks.

### Queues

```text
search
scrape
parse
ai
scoring
reports
alerts
maintenance
```

### Jobs

```text
run_search(search_run_id)
fetch_search_results(search_run_id, source_name)
fetch_listing(listing_id)
parse_listing_snapshot(listing_snapshot_id)
normalize_listing(listing_snapshot_id)
find_comparables(opportunity_id)
score_opportunity(opportunity_id)
select_candidates(search_run_id)
fetch_candidate_images(opportunity_id)
analyze_candidate_images(opportunity_id)
generate_pricing_analysis(opportunity_id)
generate_risk_analysis(opportunity_id)
generate_decision_report(opportunity_id)
send_alert(alert_id)
expire_source_snapshots()
```

### Search job flow

```text
run_search
-> fetch_search_results for AutoTrader
-> fetch_search_results for Kijiji
-> normalize listings
-> create/update opportunities
-> find comparables
-> score opportunities
-> select candidates up to configured cap, default 50
-> trigger image analysis for final candidates, up to configured image cap, default 10
-> trigger reports for high-score opportunities
-> create alerts
```

## 11. Scraping Adapter Contract

Each source adapter should implement the same interface.

```python
class ListingSourceAdapter:
    source_name: str

    async def search(self, filters: SearchFilters) -> list[SourceListingRef]:
        ...

    async def fetch_listing(self, ref: SourceListingRef) -> SourceSnapshot:
        ...

    async def parse_listing(self, snapshot: SourceSnapshot) -> ParsedListing:
        ...

    async def fetch_images(self, listing_snapshot: ListingSnapshot) -> list[SourceImage]:
        ...
```

### Adapter output requirements

Every parsed field should include:

- Value.
- Source evidence.
- Extraction method.
- Confidence.

The adapter should never silently invent values. Unknown values must be represented as null.

## 12. AI Adapter Contract

All AI calls go through one model adapter.

```python
class AiModelAdapter:
    async def structured_extract(
        self,
        task_type: str,
        prompt_version: str,
        input_payload: dict,
        output_schema: dict,
    ) -> AiResult:
        ...
```

### Required metadata

Store per AI run:

- Task type.
- Model provider.
- Model name.
- Prompt version.
- Input reference.
- Output JSON.
- Schema validation status.
- Confidence.
- Token/cost metadata where available.

## 13. Scoring Engine

The scoring engine should be deterministic and testable. AI can provide signals, but scoring must be reproducible from stored inputs.

### 13.1 Deal score components

Use a 0 to 100 score.

Recommended initial weights:

```text
profit_potential_score:      40%
resale_speed_score:          25%
risk_score_inverse:          25%
data_confidence_score:       10%
```

Dealer risk tolerance can adjust the weights:

```text
low risk tolerance:     increase risk weight, increase missing-data penalty
medium risk tolerance:  default weights
high risk tolerance:    increase profit weight, reduce missing-data penalty
```

### 13.2 Profit potential score

Inputs:

- Retail mid estimate.
- Asking price.
- Estimated costs.
- Target profit.
- Max buy price.

Example:

```text
profit_gap = max_buy_price - asking_price
```

If `profit_gap` is positive, score higher. If negative, score lower or mark overpriced.

### 13.3 Resale speed score

Inputs:

- Brand/model preference.
- Comparable listing count.
- Price band demand.
- Mileage band.
- Vehicle age.
- Seller market saturation.

Initial MVP can use rules:

- Preferred brand/model: bonus.
- Too many similar listings: small penalty.
- Mileage above peer median: penalty.
- Retail price near weighted market median: bonus.

### 13.4 Risk score

Inputs:

- Missing VIN/history/lien.
- Accident claims.
- Title brand.
- Odometer issue.
- Seller type.
- Image findings.
- Source extraction confidence.

Hard pass rules:

- Odometer issue confirmed.
- Flood/fire/irreparable title confirmed.
- VIN mismatch confirmed.
- Lien found without safe payout plan.

### 13.5 Missing-data penalty

Missing VIN/history must not block discovery ranking, but must affect confidence and score.

Penalty should scale by:

- Vehicle price.
- Dealer risk tolerance.
- Seller type.
- Whether listing claims "clean/no accident" without proof.

Example:

```text
missing_history_penalty =
  base_penalty
  * price_band_multiplier
  * risk_tolerance_multiplier
```

### 13.6 Image risk adjustment

Image analysis can adjust risk only with explanation.

Example:

```text
minor cosmetic concern:       -1 to -3 points
visible body damage:          -4 to -10 points
rust concern:                 -5 to -15 points
warning light visible:        -8 to -20 points
odometer mismatch:            hard manual review
VIN mismatch:                 hard manual review
```

Image analysis should only run for candidate opportunities selected by threshold or manual dealer action. It should not run across every listing in a broad search.

## 14. Pricing Engine

### 14.1 Comparable scoring

Initial comparable similarity weights:

```text
make/model match:          25%
trim similarity:           15%
year distance:             10%
mileage distance:          15%
location proximity:        10%
drivetrain/body style:     10%
seller/certification:      5%
history/title similarity:  10%
```

### 14.2 Weighted retail value

Use weighted median for retail mid.

Use weighted percentiles for low/high:

```text
retail_low = weighted 20th percentile
retail_mid = weighted 50th percentile
retail_high = weighted 80th percentile
```

### 14.3 Max buy price

```text
max_buy_price =
  retail_mid
  - estimated_reconditioning
  - selling_costs
  - transport_cost
  - buying_fees
  - capital_cost
  - risk_reserve
  - target_profit
```

### 14.4 Starting offer

```text
starting_offer =
  max_buy_price
  - negotiation_buffer
```

Initial negotiation buffer:

```text
private seller: 5% of max_buy_price, capped by configuration
dealer seller: 2% of max_buy_price
auction: 0 unless bid strategy is added later
```

## 15. Report Generation

Reports should be generated from canonical tables, not directly from raw scraped HTML.

Report JSON should include:

- Recommendation.
- Retail low/mid/high.
- Max buy price.
- Starting offer.
- Pricing inputs.
- Risk factors.
- Missing data.
- Section confidence.
- Comparable listings.
- Excluded comparables.
- Image findings.
- Source failure notes.
- Physical inspection checklist.

Report status:

- `preliminary` if VIN/history/lien data is missing.
- `partial` if important sources failed.
- `full` if sufficient history/lien/source data exists.
- `stale` if a newer listing snapshot or correction requires recalculation.

## 16. Alert Rules

MVP alerts are created for:

- High-score listings.
- Price drops.

Alert channels:

- In-app.
- Email.

High-score alert condition:

```text
opportunity.deal_score >= dealer_settings.candidate_score_threshold
```

Price-drop alert condition:

```text
latest_listing_snapshot.asking_price_cad < previous_listing_snapshot.asking_price_cad
```

The alert payload should include:

- Opportunity ID.
- Listing title.
- Source.
- Old price if applicable.
- New price.
- Deal score.
- Dashboard URL.

## 17. Source Snapshot Retention

Raw artifacts expire after 90 days.

Retention job:

```text
expire_source_snapshots
-> find source_snapshots where expires_at < now()
-> delete object storage artifact
-> keep metadata row with object_key nulled or tombstoned
```

Keep extracted structured facts and reports unless the dealer deletes the account or opportunity.

## 18. First Milestone Build Plan

### Milestone 1A: Schema and migrations

- Create SQLAlchemy models.
- Create Alembic migrations.
- Add seed dealer account/settings.
- Add enum validation.

### Milestone 1B: Domain services

- Create Search service.
- Create Opportunity service.
- Create Comparable service.
- Create Pricing service.
- Create Risk service.

### Milestone 1C: Scoring engine

- Implement comparable similarity scoring.
- Implement weighted median and weighted percentiles.
- Implement preliminary max-buy-price calculation.
- Implement missing-data penalty.
- Implement overpriced classification.

### Milestone 1D: API skeleton

- Settings endpoints.
- Search CRUD endpoints.
- Search run creation.
- Opportunity listing endpoint.
- Opportunity detail endpoint.
- Recalculate endpoint.

### Milestone 1E: Tests

- Unit tests for pricing.
- Unit tests for comparable scoring.
- Unit tests for missing-data penalties.
- Unit tests for report status selection.
- Integration test for search run creating ranked opportunities from fixture data.

## 19. Test Fixtures Needed Before Scraping

To build scoring before live scraping, create fixture JSON files:

```text
fixtures/
  listings/
    civic_target.json
    civic_comparables.json
    overpriced_listing.json
    missing_vin_listing.json
    image_risk_listing.json
  pricing/
    weighted_median_cases.json
  risk/
    missing_history_cases.json
```

This allows the first milestone to be implemented without waiting for scraping adapters.

## 20. Technical Risks

### Scraping reliability

Mitigation:

- Per-source adapters.
- Stored raw snapshots.
- Fixture-based parser tests.
- Partial result behavior.

### AI extraction quality

Mitigation:

- Structured schemas.
- Pydantic validation.
- Store AI run metadata.
- Use AI as signal, not final authority.

### Pricing trust

Mitigation:

- Explainable formula.
- Comparable table.
- Dealer can remove bad comparables.
- Recalculate report versions.

### Legal/source access

Mitigation:

- Source access tiering.
- Respect source terms.
- Prefer official or user-provided data.
- Avoid bypass behavior.

## 21. Immediate Next Tasks

1. Initialize backend project structure.
2. Add FastAPI, SQLAlchemy, Alembic, PostgreSQL config, and test setup.
3. Implement database schema migrations.
4. Add fixture data for one Quebec vehicle example and comparable set.
5. Implement weighted comparable scoring.
6. Implement preliminary max-buy-price calculator.
7. Expose `/api/searches`, `/api/searches/{id}/run`, and `/api/opportunities`.
8. Build a minimal dashboard view for ranked fixture-backed opportunities.
