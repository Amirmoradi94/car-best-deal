# Implementation Plan: Milestone 1

## Objective

Implement the first backend slice for the Quebec used-car opportunity finder.

This milestone intentionally starts with fixture-backed scoring and pricing so engineering can validate the core business logic before live AutoTrader/Kijiji scraping is complete.

## Scope

Milestone 1 includes:

- Backend project scaffold.
- Domain enums and schemas.
- SQLAlchemy model definitions aligned with the technical schema.
- Scoring engine.
- Pricing engine.
- Comparable similarity and weighted retail estimate.
- Missing-data penalties.
- Overpriced classification.
- Fixture-backed opportunity ranking.
- Initial FastAPI route skeleton.
- Unit tests for pricing and scoring.

Milestone 1 excludes:

- Live Zyte scraping.
- Scrapling source adapters.
- Gemini API calls.
- Authentication.
- Real PostgreSQL migrations.
- Frontend dashboard.
- PDF/CSV rendering.
- Email delivery.

## Build Sequence

### Step 1: Project Scaffold

Create:

- `pyproject.toml`
- `app/`
- `app/domain/`
- `app/services/`
- `app/db/`
- `app/api/`
- `fixtures/`
- `tests/`

### Step 2: Domain Layer

Create enums and dataclasses for:

- Seller type.
- Opportunity stage.
- Report status.
- Recommendation.
- Confidence level.
- Vehicle profile.
- Listing snapshot.
- Comparable listing.
- Dealer settings.
- Pricing analysis.
- Risk analysis.
- Scored opportunity.

### Step 3: Pricing Engine

Implement:

- Comparable similarity score.
- Weighted median.
- Weighted 20th and 80th percentiles.
- Retail low/mid/high.
- Max buy price.
- Starting offer.

### Step 4: Scoring Engine

Implement:

- Profit potential score.
- Resale speed score.
- Risk score.
- Data confidence score.
- Missing VIN/history/lien penalty.
- Image-risk adjustment hook.
- Overpriced classification.
- Final 0-100 deal score.

### Step 5: Fixtures

Create fixture data for:

- Target listing.
- Comparable listings.
- Missing VIN/history listing.
- Overpriced listing.
- Image-risk listing.

### Step 6: API Skeleton

Create route modules for:

- Settings.
- Searches.
- Opportunities.
- Reports.

The API can return fixture-backed data in this milestone.

### Step 7: SQLAlchemy Models

Create model definitions for the main MVP entities:

- DealerAccount.
- DealerSettings.
- Search.
- SearchRun.
- Listing.
- ListingSnapshot.
- VehicleProfile.
- Opportunity.
- ComparableListing.
- PricingAnalysis.
- RiskAnalysis.
- CandidateAnalysis.
- ImageAnalysis.
- DecisionReport.
- Alert.

### Step 8: Tests

Add tests for:

- Weighted median.
- Weighted percentiles.
- Comparable scoring.
- Preliminary max-buy-price calculation.
- Missing-data penalties.
- Overpriced classification.
- Fixture-backed ranked opportunity.

## Done Criteria

Milestone 1 is complete when:

- Tests pass locally.
- Fixture-backed scoring produces ranked opportunities.
- Pricing outputs retail low/mid/high, max buy price, and starting offer.
- Missing VIN/history creates a preliminary result and reduces confidence.
- Overpriced listings are identifiable.
- API skeleton imports successfully.

