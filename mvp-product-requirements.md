# MVP Product Requirements: Quebec Used Car Opportunity Finder

## 1. Product Summary

The MVP is a discovery-first web application for an independent used-car dealer in Quebec. It helps the dealer find promising used-car listings before physically visiting a vehicle.

The app searches AutoTrader Canada and Kijiji using dealer-defined criteria, ranks opportunities, estimates retail value, identifies risks, analyzes candidate listing photos, and generates a pre-visit report with a preliminary or full max-buy-price recommendation depending on available data.

## 2. Target User

Primary user:

- Independent Canadian used-car dealer operating in Quebec.

Initial geography:

- Greater Montreal.
- Dealer can configure search radius.

MVP account model:

- Single user per dealership.
- Multi-user roles are out of scope for MVP.

## 3. MVP Goals

The MVP must prove:

- A dealer can enter search criteria and receive ranked used-car opportunities.
- The system can gather and normalize listings from AutoTrader and Kijiji.
- The system can estimate retail value using comparable listings.
- The system can produce useful preliminary max-buy-price guidance.
- The system can identify candidates that deserve deeper analysis.
- The system can generate a full pre-visit report when enough data is available.

The first usable demo should prove:

- Search criteria returns ranked listings.

The first implementation milestone should be:

- Data model and scoring engine first.

## 4. Inputs

### 4.1 Primary Input: Search Criteria

The main workflow starts from search criteria, not a known VIN.

The app must support both:

- Structured filters.
- Natural-language search.

Structured filters:

- Make.
- Model.
- Year range.
- Trim.
- Price range.
- Mileage range.
- Location.
- Radius.
- Seller type.
- Accident status if available from listing data.

Natural-language examples:

- "Cheap Civics under market in Montreal."
- "Toyota Corolla under $18k, less than 120k km, Greater Montreal."
- "AWD SUVs under $25k within 50 km of Laval."

The system should convert natural language into structured filters and show the interpreted filters before running the search.

### 4.2 Secondary Inputs

The app must also support:

- VIN entry.
- AutoTrader listing URL.
- Kijiji listing URL.

Secondary inputs are used for direct analysis and report enrichment.

## 5. Data Sources

### 5.1 Listing Sources

MVP sources:

- AutoTrader Canada.
- Kijiji / Kijiji Autos.

Scraping stack:

- Zyte API for page retrieval, managed scraping, browser rendering, sessions, screenshots, and resilient access.
- Scrapling for parsing, extraction adapters, adaptive selectors, and fallback parsing.

### 5.2 Vehicle History Sources

MVP must support:

- Paid/API integration if available.
- Manual dealer input.
- PDF/document upload fallback.

Examples:

- CARFAX Canada PDF/report.
- Seller-provided documents.
- Auction condition report if available.

The app must not automatically purchase paid reports without dealer approval.

### 5.3 Quebec Lien/Title Evidence

MVP must support:

- Manual lien/title entry.
- Document upload.
- Clear "not verified" status until evidence is provided.

The app should not imply lien/title clearance unless supporting evidence exists.

### 5.4 Source Snapshots

The app must store raw source snapshots with retention:

- Raw HTML, images, and PDFs retained for 90 days.
- Extracted structured data and final reports retained separately.

## 6. Output

### 6.1 Discovery Results

Each discovery result card must show:

- Vehicle title.
- Source.
- Listing price.
- Location.
- Mileage.
- Estimated retail value.
- Deal score.
- Key missing data.
- Candidate status.

The discovery card should not overload the dealer with a full report for every listing.

### 6.2 Full Pre-Visit Report

The full report must show:

- Recommendation.
- Retail low/mid/high.
- Max buy price.
- Starting offer.
- Deal score.
- Section-level confidence.
- Risk summary.
- Comparable listings.
- Image-analysis findings when available.
- Missing data checklist.
- Lien/history verification status.
- Physical inspection checklist.
- Source evidence.

Reports must be exportable as:

- PDF.
- CSV.

## 7. Workflow

### 7.1 Discovery Workflow

1. Dealer creates or runs a search.
2. Dealer provides structured filters or natural-language search.
3. Dealer chooses the number of listings to evaluate, with a default of 25.
4. System fetches matching listings from AutoTrader and Kijiji.
5. System parses listing data.
6. System deduplicates listings.
7. System finds or extracts comparable listings.
8. System estimates retail value.
9. System scores and ranks opportunities.
10. System displays ranked opportunities.
11. High-score listings can trigger deeper analysis automatically.
12. Dealer can manually analyze any other listing.

### 7.2 Direct Analysis Workflow

1. Dealer enters VIN or listing URL.
2. System fetches or normalizes the vehicle/listing.
3. System extracts available vehicle facts.
4. System searches comparables.
5. Dealer may upload history/lien documents.
6. System generates a report.

### 7.3 Candidate Workflow

Final candidates are selected by:

- Configurable score threshold.
- Manual dealer add/remove.
- Hard cap of top 50 candidates.

For final candidates, the system:

- Scrapes listing images.
- Runs image analysis on up to 10 photos per candidate.
- Applies image findings as explained risk adjustments to the score.
- Updates the report if new risk findings are material.

### 7.4 Opportunity Stages

Each opportunity must support these workflow stages:

- New.
- Candidate.
- Needs Data.
- Contact Seller.
- Ready to Visit.
- Visited.
- Offer Made.
- Bought.
- Passed.

If key data is missing, the app should warn before moving an opportunity to Ready to Visit, but allow manual override.

## 8. Dashboard Requirements

The main dashboard must open on:

- Ranked opportunities.

Dashboard must support:

- Saved searches.
- Ranked opportunity list.
- Candidate list.
- Search refresh status.
- Alerts.
- Source failure notes.
- Seller contact status.
- Seller notes.

Seller contact tracking in MVP includes:

- Notes.
- Contact status.

Full CRM-style messaging is out of scope.

## 9. Saved Searches and Alerts

MVP must support:

- Saved searches.
- Scheduled refresh.
- Dealer-configurable schedule frequency.
- In-app alerts.
- Email alerts.

Alert triggers:

- High-score listings.
- Price drops.

Out of scope:

- SMS alerts.
- Full seller messaging automation.

## 10. Scoring and Ranking

### 10.1 Ranking Goal

Discovery ranking must use a balanced score based on:

- Profit potential.
- Expected resale speed.
- Risk.

### 10.2 Dealer Scoring Settings

Dealer can configure:

- Target profit per search.
- Risk tolerance.
- Preferred brands/models.

Full scoring-rule customization is out of scope for MVP.

### 10.3 Missing VIN/History Handling

Because discovery starts from search criteria, many listings may not expose VIN or history.

The system must:

- Still rank listings without VIN.
- Penalize missing VIN/history based on vehicle price and risk level.
- Clearly mark missing history/lien/title data.
- Allow preliminary max-buy-price estimates without VIN/history.

### 10.4 Overpriced Listings

By default:

- Hide overpriced listings.

Optional:

- Dealer can enable "include overpriced."

If included, overpriced listings should be marked as weak opportunities.

## 11. Pricing and Comparables

### 11.1 Retail Estimate

Retail value must use:

- Weighted median based on comparable similarity.

Do not use a simple average for primary valuation.

### 11.2 Comparable Count

For each evaluated vehicle, use:

- 20 to 50 comparables when available.

### 11.3 Comparable Similarity

Comparable scoring should consider:

- Make/model match.
- Year distance.
- Trim similarity.
- Mileage distance.
- Location/province.
- Seller type.
- Certification status.
- Accident/title status when known.
- Drivetrain.
- Body style.

### 11.4 Comparable Editing

Dealer must be able to:

- Remove bad comparables from the report.

When comparables are removed:

- Retail estimate recalculates.
- Max buy price recalculates.
- Report version updates.

### 11.5 Reported Pricing

Reports must show:

- Retail low.
- Retail mid.
- Retail high.
- Max buy price.
- Starting offer.

### 11.6 Max Buy Price Without VIN/History

If VIN/history/lien data is missing:

- Show max buy price as preliminary.
- Display confidence impact.
- Show missing-data checklist.

## 12. Image Analysis

### 12.1 When Image Analysis Runs

Image analysis runs only for final candidates.

Final candidate rules:

- Above configurable score threshold.
- Dealer manually selected.
- Capped at top 50 candidates.

### 12.2 Image Count

Analyze:

- Up to 10 photos per candidate.

### 12.3 Image Findings

AI image analysis should look for:

- Visible damage.
- Rust.
- Panel mismatch.
- Tire wear.
- Interior condition.
- Warning lights.
- Odometer photo.
- VIN photo if visible.

### 12.4 Score Impact

Image analysis can affect the deal score only as:

- A risk adjustment.
- With explanation and source photo reference.

The system must not silently downgrade or upgrade a vehicle based on image analysis.

## 13. AI Requirements

The AI model layer should use Gemini Flash through a configurable model adapter.

The model must be used for:

- Natural-language search interpretation.
- Listing extraction fallback.
- Vehicle-history/document extraction.
- Risk language detection.
- Comparable relevance support.
- Image analysis.
- Report explanation.

The AI model must not be the sole authority for:

- Final price calculation.
- Deterministic risk rules.
- Lien/title clearance.
- VIN verification.

All AI outputs used by the backend must be:

- Structured.
- Schema-validated.
- Stored with model name/version.
- Stored with confidence.
- Linked to source evidence.

## 14. Source Failure Behavior

If a scraper or data source fails:

- Do not hide the failure.
- Do not fail the entire report unless the primary input cannot be processed.
- Show partial result with source failure note.
- Mark affected report sections as lower confidence.

## 15. Confidence Display

Report confidence must be displayed by section:

- Listing.
- Pricing.
- History.
- Images.
- Lien.

Avoid one global confidence number as the only trust indicator.

## 16. Dealer Corrections

Dealer corrections must:

- Update the current report.
- Recalculate affected pricing/scoring fields.
- Be saved for that dealer's future reports.

Examples:

- Correct trim.
- Remove bad comparable.
- Add known accident history.
- Add lien status.
- Correct mileage.

Corrections should be stored as explicit overrides, not silent mutations of scraped source data.

## 17. Data Model Requirements

MVP should implement these core entities:

- DealerAccount.
- DealerSettings.
- Search.
- SearchRun.
- Listing.
- ListingSnapshot.
- VehicleProfile.
- ComparableListing.
- CandidateAnalysis.
- ImageAnalysis.
- HistoryProfile.
- LienProfile.
- PricingAnalysis.
- RiskAnalysis.
- DecisionReport.
- Opportunity.
- DealerCorrection.
- Alert.

## 18. Suggested Status Values

### SearchRun

- queued.
- running.
- completed.
- completed_partial.
- failed.

### Opportunity

- new.
- candidate.
- needs_data.
- contact_seller.
- ready_to_visit.
- visited.
- offer_made.
- bought.
- passed.

### DecisionReport

- preliminary.
- full.
- partial.
- stale.

## 19. Acceptance Criteria

### Discovery

- Dealer can create a search using structured filters.
- Dealer can create a search using natural language.
- Dealer can run a search for Greater Montreal with configurable radius.
- System returns ranked listings from AutoTrader and Kijiji.
- Dealer can choose number of listings to evaluate, default 25.

### Ranking

- Each listing shows deal score and estimated retail value.
- Missing VIN/history is clearly shown.
- Missing VIN/history affects score based on price/risk.
- Overpriced listings are hidden unless dealer enables include overpriced.

### Candidate Analysis

- Dealer can manually add/remove final candidates.
- System automatically selects candidates above threshold.
- Final candidate count is capped at 50.
- System analyzes up to 10 photos per candidate.
- Image findings are shown with risk explanation.

### Pricing

- Retail value uses weighted median of comparables.
- Report uses 20 to 50 comparables when available.
- Dealer can remove bad comparables.
- Removing comparables recalculates pricing.
- Report shows retail low/mid/high, max buy price, and starting offer.
- Max buy price is marked preliminary when VIN/history/lien data is missing.

### Reports

- Full report includes risks, comparables, missing data, image findings, and physical inspection checklist.
- Confidence is shown by section.
- Report exports to PDF and CSV.

### Workflow

- Dashboard opens to ranked opportunities.
- Opportunity can move through all MVP stages.
- Missing key data creates warning before Ready to Visit.
- Dealer can manually override the warning.
- Seller notes and contact status are supported.

### Alerts

- Dealer can save searches.
- Dealer can schedule searches.
- Dealer can configure refresh frequency.
- In-app and email alerts trigger for high-score listings and price drops.

### Source Handling

- Source failures produce partial reports where possible.
- Failure notes are visible.
- Raw source snapshots are retained for 90 days.

## 20. Out of Scope for MVP

- Multi-user dealership roles.
- Full CRM messaging.
- SMS alerts.
- Automated paid report purchasing without dealer approval.
- Automatic lien clearance.
- Full auction integration unless access is available early.
- Full Canada support.
- Private-buyer mode.
- Mobile app.
- Fully automated purchase decision.
- Physical inspection replacement.

## 21. Implementation Milestones

### Milestone 1: Data and Scoring Foundation

- Define database schema.
- Implement listing, vehicle, comparable, report, and opportunity models.
- Implement dealer settings.
- Implement weighted comparable scoring.
- Implement preliminary max-buy-price calculator.
- Implement missing-data penalties.

### Milestone 2: Search and Scraping Prototype

- Implement Zyte client.
- Implement Scrapling parser interface.
- Build AutoTrader adapter.
- Build Kijiji adapter.
- Store listing snapshots.
- Normalize extracted listings.

### Milestone 3: Discovery Dashboard

- Build search creation.
- Build natural-language filter interpretation.
- Build ranked opportunity list.
- Build overpriced toggle.
- Build source failure display.

### Milestone 4: Candidate Analysis

- Add candidate threshold.
- Add manual candidate add/remove.
- Scrape listing images.
- Run Gemini image analysis for up to 10 photos.
- Apply explained image-risk adjustment.

### Milestone 5: Full Report

- Build report generation.
- Add comparable table.
- Add comparable removal and recalculation.
- Add PDF/CSV export.
- Add section-level confidence.
- Add missing-data checklist.

### Milestone 6: Saved Searches and Alerts

- Add saved searches.
- Add scheduled refresh.
- Add in-app alerts.
- Add email alerts.
- Add price-drop detection.

## 22. Open Engineering Questions

- Which exact AutoTrader and Kijiji page types should be supported first?
- What is the legal/commercial access policy for each source?
- Which PDF formats should be supported first for vehicle-history upload?
- Which email provider should be used for MVP alerts?
- What default scoring weights should ship before dealer customization?
- What default target profit options should be presented in the UI?
- What object storage provider should hold raw snapshots?
- Should raw images be stored directly or referenced through expiring URLs?
