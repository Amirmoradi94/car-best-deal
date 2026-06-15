# Implementation Plan: Persisted Analysis and Profile Entities

## Goal

Close the product-requirements gap for persisted analysis/profile entities without duplicating entities already implemented under more specific names.

## Entity Audit

Already implemented as real models and services:

- `HistoryProfile`: implemented as `OpportunityHistoryProfile` plus `vehicle_history` service and opportunity history API.
- `DealerCorrection`: implemented as `DealerCorrection` plus dealer correction service/API/report integration.
- `Alert`: implemented as `Alert` plus in-app/email alert service/API.

Missing or only embedded as JSON:

- `LienProfile`: title evidence exists, but there is no normalized profile row representing current lien/title state.
- `ImageAnalysis`: image-risk results are embedded on candidate snapshots but not persisted as a first-class analysis entity.
- `CandidateAnalysis`: selected/promoted candidate analysis is not persisted as its own lifecycle row.

## Scope

1. Add SQLAlchemy models and Alembic migration for:
   - `candidate_analyses`
   - `image_analyses`
   - `lien_profiles`
2. Add services for:
   - creating candidate analysis rows when a candidate is promoted to an opportunity
   - creating image analysis rows from the candidate's image-risk result
   - creating lien profile rows from title/lien evidence
3. Expose these entities in existing opportunity payloads:
   - `candidate_analysis`
   - `image_analysis`
   - `lien_profile`
4. Keep existing HistoryProfile, DealerCorrection, and Alert implementations and document the mapping to product terminology.
5. Add focused tests for persistence, payload exposure, and migration schema.

## Data Flow

### Candidate/Image Analysis

1. Dealer promotes a candidate.
2. `promote_candidate_to_opportunity()` creates an `Opportunity`.
3. A `candidate_analyses` row is created with promotion status, selected score, and image counts.
4. An `image_analyses` row is created from persisted candidate image-risk fields.
5. Opportunity API responses include latest candidate and image analysis summaries.

### Lien Profile

1. Dealer submits title/lien evidence manually or through a document upload.
2. Existing `opportunity_title_evidence` row is persisted.
3. A `lien_profiles` row is created from the evidence, preserving normalized status, verification flag, confidence, linked evidence ID, and raw payload.
4. Opportunity API responses include latest lien profile summary.

## Acceptance Criteria

1. Promoting a candidate persists one `candidate_analyses` row and one `image_analyses` row.
2. Re-promoting the same candidate remains idempotent and does not create duplicate analysis rows.
3. Creating title evidence persists a linked `lien_profiles` row.
4. Opportunity detail includes `candidate_analysis`, `image_analysis`, and `lien_profile`.
5. Migration smoke tests assert all six required product entities are represented by real tables.
6. Existing alert, dealer correction, history profile, and report behavior continues to pass.

