# Lien and Title Evidence Workflow Implementation Plan

## Problem

The app can currently mark the lien checklist item and attach generic documents, but it has no durable workflow for what lien/title evidence says. Dealers need to record manual lien checks, PPSA/PPSR lookups, UVIP evidence, ownership verification, lender payout requirements, payout status, and final title-clearance evidence before treating a vehicle as ready to buy.

## Goals

- Add a dedicated title-clearance evidence model per opportunity.
- Support manual entry for lien/title checks and seller ownership verification.
- Link uploaded UVIP, PPSA/PPSR, payout, lien-release, and ownership documents to title evidence.
- Track lender payout requirements through requested, received, paid, and released states.
- Keep `lien_verification` as missing key data until title is actually clear/released.
- Include title evidence in opportunity responses, decision reports, dashboard cards, and report HTML.

## Non-Goals

- Real PPSA/PPSR paid provider integration.
- OCR extraction from UVIP/PPSA/PPSR PDFs.
- Legal title opinion automation.
- Payment execution or lender portal integration.

## Data Model

Create `opportunity_title_evidence`:

- `opportunity_id`
- `source_type`
- `title_clearance_status`
- `provider`
- `lookup_reference`
- `checked_at`
- `document_id`
- `seller_name`
- `registered_owner_name`
- `ownership_verified`
- `lienholder_name`
- `lien_amount_cad`
- `payout_required`
- `payout_amount_cad`
- `payout_due_date`
- `payout_status`
- `notes`
- `raw_payload`
- UUID/timestamps

## Source Types

- `manual`
- `uvip`
- `ppsa_lookup`
- `ppsr_lookup`
- `seller_ownership`
- `lender_payout`
- `lien_release`
- `document_upload`

## Clearance Statuses

- `unknown`
- `needs_review`
- `clear`
- `lien_found`
- `payout_pending`
- `payout_ready`
- `payout_paid`
- `released`
- `blocked`

Only `clear` and `released` clear `lien_verification` and mark `lien_status_checked` complete.

## API

- `POST /api/opportunities/{opportunity_id}/title-evidence`
- `GET /api/opportunities/{opportunity_id}/title-evidence`

The create route accepts manual entry fields and an optional `document_id` to link evidence to a previously uploaded document.

## Document Upload Integration

Extend document types:

- `ppsa_report`
- `ppsr_report`
- `lien_release`
- `lender_payout_statement`

When a lien/title document is uploaded, create a linked evidence row:

- UVIP/PPSA/PPSR/ownership documents -> `needs_review`
- lender payout statement -> `payout_pending`
- lien release -> `released`

## Report Integration

Decision reports should include:

- `title_evidence.latest`
- `title_evidence.evidence`
- `verification.lien_title` from title evidence when present
- risk factors for liens, pending payouts, blocked status, or unverified ownership
- HTML section for title and lien evidence

## Dashboard

Promoted opportunity cards should show:

- latest title clearance status
- owner/lienholder/payout summary
- title evidence entry form
- optional linked document selector

## Tests

- Migration smoke test verifies table and columns.
- API test creates manual clear evidence and verifies missing data/checklist/report behavior.
- API test records lien found with payout pending and verifies blocker remains.
- Document upload test verifies UVIP creates evidence that needs review, lien release clears.
- Dashboard static test verifies title-evidence controls.

## Acceptance Criteria

- A dealer can record title-clearance evidence without uploading a document.
- A dealer can upload lien/title documents and see linked evidence.
- Lien/title is not considered resolved until status is `clear` or `released`.
- Lender payout and seller ownership fields appear in API/report/dashboard payloads.
- Full test suite passes.
