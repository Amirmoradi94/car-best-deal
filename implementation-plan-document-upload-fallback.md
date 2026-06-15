# Document Upload Fallback Implementation Plan

## Problem

Dealers can promote candidates, manage visit readiness, enter structured history facts, and generate decision reports. They cannot attach source documents when integrations or structured parsing are unavailable. This blocks practical use for CARFAX PDFs, UVIP documents, seller attachments, mechanic quotes, auction condition reports, service invoices, and ownership paperwork.

## Goals

- Add a generic upload fallback tied to promoted opportunities.
- Preserve original uploaded files in the object store.
- Store searchable document metadata in the database.
- Surface uploaded evidence in opportunity responses, the dashboard, and decision reports.
- Let strong evidence types update existing checklist/missing-data workflow state without claiming OCR or parsing occurred.

## Non-Goals

- OCR or PDF extraction.
- Vendor API integrations.
- Virus scanning or malware detonation.
- Multi-dealer authentication/authorization beyond the app's current default dealer model.
- Replacing the structured history profile flow.

## Backend Plan

1. Add `opportunity_documents`.
   - `opportunity_id`
   - `document_type`
   - `original_filename`
   - `content_type`
   - `size_bytes`
   - `sha256`
   - `object_key`
   - `notes`
   - `metadata_json`
   - timestamps and UUID primary key

2. Add supported document types.
   - `carfax_pdf`
   - `uvip`
   - `seller_document`
   - `mechanic_quote`
   - `auction_condition_report`
   - `service_invoice`
   - `ownership_document`

3. Add storage service.
   - Validate type and MIME.
   - Enforce max size through `DOCUMENT_UPLOAD_MAX_BYTES`.
   - Sanitize filenames.
   - Store bytes under `opportunities/{opportunity_id}/documents/...`.
   - Return stable JSON payloads and download URLs.

4. Update workflow state.
   - CARFAX upload checks history and clears `vehicle_history`.
   - UVIP/ownership upload checks lien/title and clears `lien_verification`.
   - Service invoice marks service records requested.
   - Seller/ownership docs mark VIN confirmed.

5. Add routes.
   - `POST /api/opportunities/{opportunity_id}/documents`
   - `GET /api/opportunities/{opportunity_id}/documents`
   - `GET /api/opportunities/{opportunity_id}/documents/{document_id}/download`

6. Update decision reports.
   - Include uploaded documents in `report_json.evidence.uploaded_documents`.
   - Render an Uploaded Evidence section in report HTML.
   - Show verification status as `document_uploaded` when applicable.
   - Mark latest report stale after upload.

## Dashboard Plan

1. Add a Documents block to each promoted opportunity card.
2. Show uploaded document type, filename, and download link.
3. Provide type selector, file picker, notes field, and upload button.
4. Refresh opportunity state after upload so checklist, missing data, and report status update immediately.

## Tests

1. Migration smoke test verifies `opportunity_documents`.
2. API test uploads a CARFAX PDF and UVIP, lists them, downloads stored bytes, checks stale report and workflow side effects.
3. API test rejects unsupported document types and unknown opportunities/documents.
4. Dashboard static test verifies upload controls and JavaScript hooks are shipped.

## Acceptance Criteria

- Dealers can upload all required fallback document classes against an opportunity.
- Uploaded bytes can be downloaded unchanged.
- Opportunity API responses include document summaries.
- Reports include uploaded evidence.
- Existing test suite passes with SQLite and fixture mode.
