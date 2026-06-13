# Pre-Visit Used Car Evaluation Automation System

This document designs a system that automates the research phase before physically visiting a used car in Canada. It combines web scraping, structured extraction, AI analysis, and dealer scoring to decide whether a vehicle is worth inspecting in person.

The target stack requested for the product:

- Zyte API for managed scraping, browser rendering, unblocking, sessions, screenshots, and page retrieval.
- Scrapling for adaptive parsing, selector-based extraction, crawl orchestration, and fallback parsing.
- Gemini Flash model for structured extraction, normalization, reasoning, risk classification, and recommendation summaries.

The AI model should be configurable. The product can default to the requested Gemini Flash model name, but the system should keep model IDs in configuration so changing from one Gemini Flash generation to another does not require application code changes.

## Product Goal

Given a car listing URL, VIN, or search criteria, the system should collect enough online evidence to produce:

- Vehicle identity profile.
- Seller and listing profile.
- Market comparison.
- History and risk profile.
- Estimated reconditioning assumptions.
- Expected resale price.
- Maximum recommended buy price.
- Confidence score.
- Buy / buy only cheap / pass recommendation.
- Clear explanation of missing data and required physical checks.

The product does not replace physical inspection. It decides whether the car is worth visiting and what price ceiling should be used before negotiation.

## Automation Boundary

### Automated before visit

- Scrape listing data.
- Extract vehicle details from listing text and photos.
- Decode and validate VIN when available.
- Pull or ingest paid vehicle-history reports where account access exists.
- Search comparable retail listings.
- Search wholesale or auction references where dealer access exists.
- Check recall sources.
- Check lien/title sources where API or manual upload is available.
- Normalize all data into one vehicle profile.
- Use AI to identify inconsistencies, risks, and likely missing details.
- Estimate resale value and maximum buy price.
- Generate a dealer-ready pre-visit report.

### Not fully automated

- Final mechanical inspection.
- Structural/frame inspection.
- Rust and underbody inspection.
- Lien payout execution.
- Physical VIN verification.
- Seller identity verification.
- Test drive.
- Final purchase decision.

The system should make these limits visible in the final report.

## User Personas

### Independent used-car dealer

Needs fast triage across many opportunities. Values speed, margin estimates, and risk alerts.

### Dealer buyer / acquisition manager

Needs ranked leads, wholesale comparison, auction alternatives, and repeatable offer calculations.

### Small dealership owner

Needs a simple decision report with evidence, links, and recommended next action.

### Future private-buyer mode

Could use a simplified version of the same workflow, but the first product should focus on dealer economics.

## Core User Workflows

### Workflow 1: Evaluate one listing URL

1. User submits listing URL.
2. System scrapes page through Zyte.
3. Scrapling parses listing fields and page content.
4. AI extracts missing or ambiguous details from text and page screenshot.
5. System identifies VIN if present.
6. System enriches vehicle from available sources.
7. System searches comparable listings.
8. System calculates resale estimate, risks, and maximum buy price.
9. User receives a pre-visit report.

### Workflow 2: Evaluate by VIN

1. User submits VIN.
2. System decodes VIN.
3. System searches listing sources for matching VIN if allowed.
4. System ingests CARFAX Canada or uploaded history report if available.
5. System checks recalls and available title/lien sources.
6. System searches market comparables.
7. User receives risk and pricing report.

### Workflow 3: Daily opportunity monitor

1. User defines search criteria.
2. System crawls selected marketplaces on a schedule.
3. System deduplicates listings.
4. System scores each listing.
5. High-potential cars are pushed to an acquisition dashboard.
6. Dealer reviews only the top-ranked opportunities.

### Workflow 4: Upload external documents

1. User uploads CARFAX Canada PDF, UVIP, mechanic quote, or auction report.
2. AI extracts structured facts.
3. System links document facts to the existing vehicle profile.
4. Report confidence increases and recommendation is recalculated.

## System Architecture

```text
                  User / Dealer
                       |
                       v
              Web App / API Gateway
                       |
                       v
              Evaluation Orchestrator
                       |
       +---------------+----------------+
       |               |                |
       v               v                v
 Scraping Layer   Enrichment Layer   AI Analysis Layer
 Zyte + Scrapling VIN/Recall/History Gemini Flash
       |               |                |
       +---------------+----------------+
                       |
                       v
              Normalized Data Store
                       |
                       v
             Pricing + Risk Engine
                       |
                       v
              Dealer Decision Report
```

## Main Services

### 1. Web App

Responsibilities:

- Accept listing URLs, VINs, search criteria, and uploaded documents.
- Show job status.
- Show extracted data with source links.
- Let users correct bad fields.
- Display final recommendation.
- Maintain watchlists and opportunity dashboards.

Key screens:

- New evaluation.
- Evaluation report.
- Comparable listings.
- Risk evidence.
- Buy-price calculator.
- Lead monitor.
- Source health dashboard.

### 2. API Gateway

Responsibilities:

- Authentication and authorization.
- Rate limiting per user.
- Request validation.
- Job creation.
- File upload handling.
- Webhook endpoint for async completion events.

### 3. Evaluation Orchestrator

Responsibilities:

- Own the evaluation state machine.
- Decide which jobs need to run.
- Fan out scraping and enrichment jobs.
- Retry failed sources.
- Record source-level confidence.
- Trigger report generation.

Recommended state machine:

```text
created
-> source_discovery
-> scraping
-> extraction
-> enrichment
-> comparable_search
-> scoring
-> report_ready
```

Error states:

```text
blocked_missing_vin
blocked_source_login_required
partial_report_ready
failed
```

### 4. Scraping Layer

The scraping layer should use both Zyte and Scrapling, but with distinct roles.

#### Zyte role

Use Zyte when the system needs:

- Managed unblocking.
- Browser-rendered HTML.
- Screenshots.
- JavaScript execution.
- Sessions/cookies.
- Geolocation or country-specific retrieval.
- Network capture for data-loaded listing pages.
- More resilient access to dynamic sites.

#### Scrapling role

Use Scrapling when the system needs:

- Fast parsing of returned HTML.
- Adaptive selectors.
- Field extraction from known listing templates.
- Lightweight crawling.
- Fallback parsing when page structure changes.
- Reusable extraction modules per source.

#### Scraping strategy

```text
Input URL
-> classify source
-> choose source adapter
-> fetch page through Zyte if remote page is dynamic or protected
-> parse with Scrapling source adapter
-> if extraction confidence is low, send HTML/text/screenshot to AI extractor
-> store raw response snapshot and extracted fields
```

### 5. Source Adapter Layer

Each source should have its own adapter. Avoid one giant scraper.

Adapter responsibilities:

- URL validation.
- Fetch strategy.
- Selector rules.
- AI fallback rules.
- Field mapping.
- Rate limits.
- Terms and access constraints.
- Test fixtures.

Suggested adapters:

- AutoTrader listing adapter.
- AutoTrader search adapter.
- CarGurus listing adapter.
- Kijiji listing adapter.
- Facebook Marketplace adapter only if compliant access is available.
- Dealer website generic adapter.
- Dealer website source-specific adapters for common platforms.
- Auction source adapter for dealer-authenticated sources.
- CARFAX report ingestion adapter.
- UVIP document ingestion adapter.
- Recall lookup adapter.

### 6. Enrichment Layer

Responsibilities:

- VIN decode.
- Recall lookup.
- Vehicle history ingestion.
- Lien/title check ingestion.
- Market comparable search.
- Wholesale data ingestion.
- Currency and tax normalization.
- Province normalization.

The enrichment layer should accept both direct API data and manually uploaded documents because some sources may not provide practical APIs.

### 7. AI Analysis Layer

Use Gemini Flash for structured reasoning and extraction, not as the only source of truth.

AI tasks:

- Extract listing facts from unstructured text.
- Interpret seller descriptions.
- Detect risk language.
- Normalize trim and options.
- Compare listing claims against history data.
- Extract facts from PDFs and screenshots.
- Summarize accident history.
- Classify seller risk.
- Identify missing data.
- Produce report explanations.

AI should output structured JSON using a strict schema. The backend should validate every AI response before using it.

Do not let AI directly decide the final price without deterministic calculations around it. AI can estimate, explain, and classify, but the pricing engine should own the final formula.

### 8. Pricing and Risk Engine

Responsibilities:

- Calculate expected retail price range.
- Estimate wholesale support.
- Estimate reconditioning reserve.
- Estimate after-sale risk reserve.
- Calculate maximum buy price.
- Apply risk discounts.
- Generate final recommendation.

Core output:

```text
expected_retail_low
expected_retail_mid
expected_retail_high
estimated_reconditioning
risk_reserve
target_profit
maximum_buy_price
recommended_starting_offer
recommendation
confidence
```

Recommendation classes:

- `buy`
- `buy_only_cheap`
- `pass`
- `needs_more_data`

## Data Model

### VehicleEvaluation

```json
{
  "id": "eval_123",
  "status": "report_ready",
  "input_type": "listing_url",
  "input_value": "https://example.com/listing",
  "province": "ON",
  "created_at": "2026-06-12T10:00:00Z",
  "completed_at": "2026-06-12T10:03:20Z"
}
```

### VehicleProfile

```json
{
  "vin": "2HGFC2F59LH000000",
  "year": 2020,
  "make": "Honda",
  "model": "Civic",
  "trim": "EX",
  "body_style": "Sedan",
  "engine": "2.0L I4",
  "transmission": "CVT",
  "drivetrain": "FWD",
  "mileage_km": 85000,
  "exterior_color": "White",
  "interior_color": "Black"
}
```

### ListingSnapshot

```json
{
  "source": "autotrader",
  "url": "https://example.com/listing",
  "seller_type": "private",
  "seller_name": "Unknown",
  "asking_price_cad": 18500,
  "location": "Toronto, ON",
  "description": "Clean car, no accidents...",
  "photos": [],
  "scraped_at": "2026-06-12T10:01:00Z",
  "extraction_confidence": 0.91
}
```

### HistoryProfile

```json
{
  "accident_claims": [
    {
      "date": "2023-03-12",
      "amount_cad": 3200,
      "description": "Collision damage"
    }
  ],
  "title_brand": "clean",
  "owners_count": 2,
  "registration_provinces": ["ON"],
  "odometer_issues": false,
  "service_records_count": 8,
  "lien_status": "unknown"
}
```

### ComparableListing

```json
{
  "source": "autotrader",
  "url": "https://example.com/comp",
  "year": 2020,
  "make": "Honda",
  "model": "Civic",
  "trim": "EX",
  "mileage_km": 81000,
  "asking_price_cad": 19200,
  "location": "Mississauga, ON",
  "seller_type": "dealer",
  "accident_status": "clean_or_unknown",
  "similarity_score": 0.87
}
```

### DecisionReport

```json
{
  "recommendation": "buy_only_cheap",
  "confidence": 0.74,
  "expected_retail_mid_cad": 18500,
  "maximum_buy_price_cad": 13800,
  "recommended_starting_offer_cad": 12500,
  "top_risks": [
    "Accident claim exists",
    "Lien status not verified",
    "Tires not confirmed"
  ],
  "required_physical_checks": [
    "Cold start",
    "Frame rail inspection",
    "Brake and tire measurement"
  ]
}
```

## Source Collection Design

### Listing sources

Use listing sources to gather asking prices, seller claims, photos, and market supply.

Sources:

- AutoTrader.ca.
- CarGurus Canada.
- Kijiji.
- Facebook Marketplace where compliant access exists.
- Dealer websites.
- Auction listing pages where dealer access exists.

Collected fields:

- URL.
- Source.
- Asking price.
- Seller type.
- Seller name if public.
- Location.
- Listing age if available.
- VIN if public.
- Year/make/model/trim.
- Mileage.
- Description.
- Photo URLs or screenshot references.
- Disclosure text.
- Certification status.
- Accident claims mentioned by seller.

### History sources

Some history sources may require paid account access or manual upload.

Sources:

- CARFAX Canada report.
- Provincial lien/PPSA/PPSR source.
- Ontario UVIP where relevant.
- IBC VIN Verify.
- NICB VINCheck for U.S.-linked vehicles.
- Auction condition reports.
- Seller-provided service invoices.

Collected fields:

- Accident claims.
- Claim values.
- Registration events.
- Odometer events.
- Service records.
- Title brand.
- Import history.
- Lien status.
- Owner count.

### Recall sources

Sources:

- Transport Canada recall search.
- OEM recall portal.
- CARFAX recall check where available.

Collected fields:

- Open recall count.
- Recall description.
- Safety severity.
- Remedy availability.
- Completion status.

### Wholesale sources

Sources:

- Canadian Black Book.
- Manheim Canada.
- OPENLANE Canada / ADESA / TradeRev.
- Internal dealer sale history.

Collected fields:

- Wholesale estimate.
- Auction sale range.
- Bid activity.
- Recent sale price.
- Condition grade.
- Transportation cost.
- Auction fees.

## AI Extraction Schemas

### ListingExtraction schema

```json
{
  "vehicle": {
    "year": "number|null",
    "make": "string|null",
    "model": "string|null",
    "trim": "string|null",
    "mileage_km": "number|null",
    "vin": "string|null",
    "drivetrain": "string|null",
    "transmission": "string|null",
    "engine": "string|null",
    "exterior_color": "string|null"
  },
  "listing": {
    "asking_price_cad": "number|null",
    "seller_type": "dealer|private|auction|unknown",
    "location": "string|null",
    "certified": "boolean|null",
    "as_is": "boolean|null"
  },
  "claims": {
    "no_accidents_claimed": "boolean|null",
    "service_records_claimed": "boolean|null",
    "single_owner_claimed": "boolean|null",
    "needs_repair_claimed": "boolean|null"
  },
  "risks": [
    {
      "type": "string",
      "evidence": "string",
      "severity": "low|medium|high"
    }
  ],
  "missing_fields": ["string"]
}
```

### HistoryExtraction schema

```json
{
  "title_brand": "clean|rebuilt|salvage|flood|fire|irreparable|unknown",
  "accidents": [
    {
      "date": "string|null",
      "amount_cad": "number|null",
      "description": "string|null",
      "severity": "minor|moderate|major|unknown"
    }
  ],
  "owners_count": "number|null",
  "odometer_issue": "boolean|null",
  "service_record_count": "number|null",
  "registration_provinces": ["string"],
  "lien_status": "clear|lien_found|unknown"
}
```

### RiskAnalysis schema

```json
{
  "risk_score": "number",
  "pricing_penalty_cad": "number",
  "recommendation_modifier": "none|discount|pass|needs_more_data",
  "risk_factors": [
    {
      "name": "string",
      "severity": "low|medium|high|critical",
      "evidence": "string",
      "source_id": "string|null"
    }
  ],
  "missing_verifications": ["string"]
}
```

## AI Prompting Strategy

Use small, isolated AI calls instead of one large prompt that does everything.

Recommended AI jobs:

1. Listing extractor.
2. Screenshot/photo text extractor.
3. Vehicle-history extractor.
4. Comparable relevance scorer.
5. Risk analyzer.
6. Dealer report writer.

Each AI job should:

- Use structured output.
- Include source text and metadata.
- Return confidence per field.
- Quote short evidence snippets.
- Avoid inventing missing values.
- Mark unknowns explicitly.

The report writer should only use normalized backend data, not raw untrusted web text alone.

## Pricing Engine Design

### Comparable filtering

A comparable should be scored using:

- Same make/model.
- Same or adjacent year.
- Same trim or equivalent trim.
- Mileage distance.
- Same province or nearby region.
- Same drivetrain.
- Similar title/accident status.
- Similar seller type.
- Similar certification status.

Example similarity score weights:

```text
Model match:             25%
Trim match:              15%
Year distance:           10%
Mileage distance:        15%
Province/location:       10%
Drivetrain:              5%
History/title status:    10%
Seller/certification:    10%
```

### Retail estimate

Use a weighted median rather than a simple average.

```text
expected_retail_mid = weighted_median(comparable_prices, similarity_score)
expected_retail_low = 20th percentile of weighted comparables
expected_retail_high = 80th percentile of weighted comparables
```

### Risk discounts

Apply deterministic discounts for known risks.

Example:

```text
accident_minor:           2% to 4%
accident_moderate:        5% to 10%
major_claim:              10% to 20%
rebuilt_title:            25%+ or pass
unknown_lien_status:      hold report as needs_more_data
open_safety_recall:       downtime reserve
odometer_issue:           pass
flood/fire/irreparable:   pass
```

These should be configurable by province, dealer policy, brand, and price band.

### Maximum buy price

```text
maximum_buy_price =
  expected_retail_mid
  - estimated_reconditioning
  - selling_costs
  - transport_cost
  - auction_or_buying_fees
  - floorplan_or_capital_cost
  - risk_reserve
  - target_profit
```

### Starting offer

```text
recommended_starting_offer =
  maximum_buy_price
  - negotiation_buffer
```

The negotiation buffer can vary based on seller type and listing age.

## Risk Scoring Design

### Risk categories

- Title risk.
- Lien risk.
- Accident risk.
- Odometer risk.
- Import risk.
- Seller risk.
- Reconditioning risk.
- Market liquidity risk.
- Source confidence risk.
- Compliance risk.

### Confidence scoring

Confidence should be separate from risk.

Example:

```text
high risk + high confidence = likely pass
high risk + low confidence = needs more data
low risk + low confidence = maybe inspect only if price is strong
low risk + high confidence = strong candidate
```

### Red flags that should force pass or manual review

- Odometer inconsistency.
- Flood, fire, or irreparable branding.
- Lien found without safe payout plan.
- VIN mismatch.
- Seller refuses VIN.
- Title brand hidden in listing.
- Major structural damage disclosure.
- Price is far below market with incomplete history.
- AI/source disagreement on year, trim, mileage, or VIN.

## Deduplication and Identity Resolution

The same car may appear on multiple platforms.

Deduplication keys:

- VIN.
- Phone number or dealer profile where available.
- Listing photos similarity.
- Mileage.
- Price.
- Location.
- Description similarity.
- Plate if visible and legally usable.

Use deterministic VIN matching first. Use fuzzy matching only to propose duplicates, not to merge records automatically unless confidence is high.

## Data Quality Controls

Every extracted field should store:

- Value.
- Source.
- Extraction method: selector, API, AI, user, document.
- Confidence.
- Timestamp.
- Raw evidence reference.

Example:

```json
{
  "field": "mileage_km",
  "value": 85000,
  "source": "listing_snapshot_123",
  "method": "scrapling_selector",
  "confidence": 0.96,
  "evidence": "85,000 km",
  "observed_at": "2026-06-12T10:02:00Z"
}
```

If sources disagree, keep all values and mark the canonical value as unresolved until confidence rules choose a winner or a user reviews it.

## Compliance and Legal Considerations

The product must be designed conservatively.

Required practices:

- Respect each website's terms of service and robots policies.
- Prefer official APIs, dealer feeds, licensed data, and user-provided documents when possible.
- Do not bypass authentication or access controls.
- Store only the data needed for evaluation.
- Treat VINs, seller contact details, uploaded documents, and transaction details as sensitive data.
- Follow Canadian privacy obligations, including PIPEDA where applicable.
- Keep audit logs for data access and report generation.
- Allow deletion of user-uploaded documents.
- Separate personally identifiable seller data from vehicle valuation data where possible.

## Source Access Tiers

Not every source should be treated the same. The product should classify sources by access type before any connector is built.

### Tier 1: Official API or licensed feed

Best for production use.

Examples:

- Paid data feeds.
- Dealer inventory feeds.
- Auction partner access.
- Official valuation APIs.
- Official recall APIs or structured recall sources.

Rules:

- Prefer these sources when commercially possible.
- Store contract limits with the connector configuration.
- Track request quotas and usage cost.

### Tier 2: Authenticated user-provided access

Useful when the dealer already has legitimate access.

Examples:

- Dealer auction account.
- User-uploaded CARFAX Canada PDF.
- User-uploaded UVIP.
- User-uploaded seller documents.

Rules:

- Do not store raw credentials unless absolutely required.
- Prefer OAuth, temporary session tokens, or manual upload where possible.
- Keep clear audit logs showing which user provided access.

### Tier 3: Public web pages

Useful for retail listing discovery and comparable research.

Examples:

- Public vehicle listing pages.
- Public dealer inventory pages.
- Public recall pages.

Rules:

- Respect source terms, rate limits, and robots policies.
- Use conservative crawling rates.
- Cache snapshots to avoid repeated requests.
- Attribute extracted facts to their source URL.

### Tier 4: Restricted or high-risk sources

Avoid unless there is a clear legal and commercial basis.

Examples:

- Pages requiring bypassing access controls.
- Personal social profiles.
- Sources that prohibit automated access.
- Data that includes unnecessary personal information.

Rules:

- Do not build bypass behavior.
- Require manual review before enabling.
- Prefer user-provided screenshots or documents when allowed.

## Non-Functional Requirements

### Reliability

- A single failed source should not fail the entire report.
- Reports should support partial completion.
- Source failures should be visible to the user.
- Scraper adapters should have fixtures and regression tests.

### Latency

Target response times:

- Single listing quick extraction: under 60 seconds.
- Full pre-visit report with comparables: 2 to 5 minutes.
- Daily monitor batch: asynchronous, no real-time requirement.

### Accuracy

- High-confidence fields should come from structured selectors, official APIs, or uploaded documents.
- AI-extracted fields should be validated and marked with confidence.
- Pricing recommendations should be explainable and reproducible.

### Maintainability

- Each marketplace should have a separate adapter.
- Each adapter should have its own tests and fixtures.
- Pricing rules should be configuration-driven.
- AI prompts and schemas should be versioned.

### Scalability

- Use async jobs for scraping and AI calls.
- Queue jobs per source to enforce source-specific rate limits.
- Cache comparable searches.
- Store raw snapshots separately from normalized records.

### Auditability

- Every recommendation should be reproducible from stored source snapshots, normalized fields, pricing rules, and AI model versions.
- User overrides should create new report versions instead of mutating old reports silently.

## Security Design

### Secrets

Store these in a secrets manager:

- Zyte API key.
- Gemini API key.
- Marketplace credentials if allowed.
- Dealer auction credentials if allowed.
- Document storage signing keys.

Never store credentials in source code or logs.

### Data storage

Recommended storage:

- PostgreSQL for normalized vehicle, listing, scoring, and report data.
- Object storage for raw HTML, screenshots, PDFs, and report artifacts.
- Redis or equivalent for job queues, cache, and rate limiting.
- Vector store only if needed later for document search and historical comparable retrieval.

### Audit logging

Log:

- User who requested evaluation.
- Sources accessed.
- Documents uploaded.
- AI model version used.
- Report version.
- Field overrides by users.
- Final recommendation changes.

## Observability

Track:

- Scrape success rate by source.
- Extraction confidence by source.
- AI schema validation failure rate.
- Cost per evaluation.
- Time to report.
- Comparable count.
- Report confidence.
- User override rate.
- Buy recommendation acceptance.
- Post-sale profit/loss where user provides outcome.

These metrics are important because scraping and AI systems degrade quietly when source pages change.

## Cost Controls

Cost risks:

- Browser-rendered Zyte requests.
- Screenshots.
- AI calls on large HTML pages.
- Repeated comparable searches.
- Paid history reports.

Controls:

- Cache source snapshots.
- Strip boilerplate before AI calls.
- Use selectors before AI fallback.
- Batch comparable extraction.
- Use cheaper AI calls for extraction and reserve stronger calls for final reasoning if needed.
- Limit recrawls with TTLs.
- Store fingerprints to avoid reprocessing identical pages.

## Suggested Processing Pipeline

```text
1. Create evaluation
2. Normalize input
3. Fetch primary listing
4. Extract listing fields
5. Validate VIN if available
6. Decode vehicle identity
7. Search comparable listings
8. Fetch comparable listing pages
9. Score comparable relevance
10. Ingest history/lien/recall sources
11. Detect contradictions and missing data
12. Estimate retail price range
13. Estimate risk and reconditioning reserve
14. Calculate max buy price
15. Generate dealer report
16. Store report and notify user
```

## Report Design

The final report should be concise and evidence-based.

### Report sections

1. Recommendation.
2. Maximum buy price.
3. Vehicle identity.
4. Seller/listing summary.
5. Market comparison.
6. History and title risk.
7. Lien and recall status.
8. Reconditioning assumptions.
9. Missing data.
10. Required physical inspection checklist.
11. Source evidence.

### Example headline

```text
Recommendation: Buy only cheap
Max buy price: $13,800 CAD
Starting offer: $12,500 CAD
Confidence: 74%
Reason: Retail value is supported, but accident history and unverified lien status require discount and verification before payment.
```

## MVP Scope

### MVP 1: Single listing evaluator

Build:

- Submit one URL.
- Scrape primary listing with Zyte.
- Parse with Scrapling.
- AI fallback extraction.
- Manual VIN entry.
- Comparable search from one or two sources.
- Basic pricing formula.
- PDF/HTML report.

Do not build yet:

- Full daily crawler.
- Auction integrations.
- Automated lien purchase.
- User team management.
- CRM pipeline.

### MVP 2: Dealer dashboard

Add:

- Saved evaluations.
- Watchlists.
- Lead ranking.
- User field corrections.
- Source health metrics.
- Document upload.

### MVP 3: Data enrichment and learning

Add:

- CARFAX/UVIP upload extraction.
- Recall lookup.
- Wholesale integrations.
- Outcome tracking.
- Profit/loss feedback loop.
- Better brand-specific reconditioning models.

### MVP 4: Acquisition automation

Add:

- Scheduled marketplace searches.
- Alerts for high-score leads.
- Seller messaging templates.
- Dealer pipeline stages.
- Multi-user roles.

## Recommended Initial Tech Stack

Backend:

- Python service for scraping, extraction, AI orchestration, and pricing.
- FastAPI for API endpoints.
- PostgreSQL for structured data.
- Redis + worker queue for async jobs.
- Object storage for HTML, screenshots, PDFs, and reports.

Scraping:

- Zyte API fetch client.
- Scrapling parser adapters.
- Per-source adapter modules.
- Snapshot fixtures for scraper tests.

AI:

- Gemini Flash through a model adapter.
- Strict JSON Schema outputs.
- Pydantic validation.
- Retry with repair prompt only when schema validation fails.

Frontend:

- Dealer-focused dashboard.
- Compact report view.
- Evidence-first UI.
- Editable extracted fields.
- Comparison table.

## Testing Strategy

### Unit tests

- VIN normalization.
- Price parsing.
- Mileage parsing.
- Province parsing.
- Comparable scoring.
- Buy-price calculation.
- Risk-rule application.

### Scraper tests

- Fixture-based parser tests for each source.
- Snapshot tests for HTML samples.
- Failure tests for missing VIN, missing price, removed listing, and layout changes.

### AI tests

- Schema validation tests.
- Golden extraction examples.
- Hallucination checks for missing fields.
- Contradiction detection tests.

### End-to-end tests

- Listing URL to report.
- VIN-only to report.
- Uploaded CARFAX PDF to report.
- Partial-data report.
- Source failure report.

## Key Product Decisions

### Store raw evidence

Store raw snapshots and evidence references. Dealer users need to trust why the system made a recommendation.

### Prefer structured extraction before AI

Selectors and known adapters are cheaper, faster, and more controllable. AI should handle ambiguity and summarization.

### Keep recommendation explainable

Every discount, risk, and pass decision should point to evidence.

### Design for partial reports

Some sources will fail or require paid access. A partial but honest report is better than blocking everything.

### Separate risk from confidence

A risky car can be confidently risky. A low-risk car with missing data should not be treated as safe.

## Open Questions

- Which provinces should MVP support first?
- Will the product have dealer access to auction platforms?
- Will users upload CARFAX Canada reports manually, or should account integration be pursued?
- Should the system purchase paid reports automatically or only after user approval?
- What target profit should be default by price band?
- What brands/models should have special risk rules first?
- What listing sources are legally and commercially acceptable to scrape?
- Should reports be optimized for internal dealer use only or for sharing with lenders/partners?

## First Implementation Milestones

1. Define canonical data schemas.
2. Build evaluation job model and state machine.
3. Build Zyte fetch client.
4. Build Scrapling parser interface.
5. Implement one source adapter.
6. Add Gemini structured extraction adapter.
7. Build comparable scoring.
8. Build max-buy-price calculator.
9. Generate the first HTML report.
10. Add source fixtures and tests.

## References

- Zyte API documentation: https://docs.zyte.com/zyte-api/
- Zyte browser automation documentation: https://docs.zyte.com/zyte-api/usage/browser.html
- Zyte automatic extraction documentation: https://docs.zyte.com/zyte-api/usage/extract/
- Scrapling documentation: https://scrapling.readthedocs.io/en/latest/
- Gemini structured output documentation: https://ai.google.dev/gemini-api/docs/structured-output
- Gemini model documentation: https://ai.google.dev/gemini-api/docs/models
