# Recall/Compliance Checks Implementation Plan

## Goal

Add a working recall and Canadian import-compliance evidence workflow for opportunities. The first release is document/manual-entry backed and integration-ready: it stores Transport Canada/OEM recall lookup outcomes, recall completion status, import compliance/RIV evidence, and report-ready risk signals without depending on paid or brittle external portals.

## Current Gaps

- VIN analysis marks recall lookup as blocked/not configured, but opportunities have no recall/compliance evidence model.
- Decision reports always show recall as `not_checked`.
- Document upload does not classify Transport Canada recall reports, OEM portal screenshots, recall completion receipts, RIV/import compliance documents, or statement-of-compliance evidence.
- Dashboard users cannot manually record recall lookup results, completion evidence, or import compliance state.

## Data Model

Create `opportunity_recall_compliance_evidence` with:

- Opportunity/document linkage: `opportunity_id`, optional `document_id`.
- Source fields: `source_type`, `provider`, `lookup_reference`, `checked_at`.
- Recall fields: `recall_status`, `campaign_number`, `campaign_description`, `remedy_status`, `completion_date`.
- Import/compliance fields: `compliance_status`, `import_country`, `import_form`, `riv_case_number`, `inspection_required`, `inspection_deadline`.
- Audit/details: `notes`, `raw_payload`, timestamps.

Allowed source types:

- `manual`
- `transport_canada`
- `oem_portal`
- `dealer_service`
- `import_compliance`
- `riv`
- `document_upload`

Allowed recall statuses:

- `unknown`
- `not_checked`
- `no_open_recalls`
- `open_recall`
- `incomplete`
- `completed`
- `needs_review`

Allowed compliance statuses:

- `unknown`
- `not_applicable`
- `compliant`
- `non_compliant`
- `needs_inspection`
- `import_pending`
- `blocked`

Allowed remedy statuses:

- `unknown`
- `not_required`
- `required`
- `scheduled`
- `completed`
- `parts_unavailable`

## Workflow Rules

- Clear states remove the `recall_compliance` missing-data blocker:
  - recall status is `no_open_recalls` or `completed`
  - and compliance status is `not_applicable` or `compliant`
- Risk/blocked states add or keep `recall_compliance`:
  - open/incomplete/needs-review recalls
  - remedy required/scheduled/parts unavailable
  - non-compliant, needs-inspection, import-pending, or blocked import state
- Clear evidence marks `history_report_checked` only for history documents; recall/compliance evidence has its own summary and report section.
- Any evidence change marks the latest decision report stale.

## API

Add:

- `POST /api/opportunities/{opportunity_id}/recall-compliance`
- `GET /api/opportunities/{opportunity_id}/recall-compliance`

Extend opportunity payloads with:

- `recall_compliance.status`
- `recall_compliance.count`
- `recall_compliance.latest`
- `recall_compliance.evidence`

Extend document upload response with optional `recall_compliance` evidence when a supported document type is uploaded.

## Document Upload Ingestion

Add document types:

- `transport_canada_recall_report`
- `oem_recall_report`
- `recall_completion_receipt`
- `import_compliance_document`
- `riv_inspection`
- `statement_of_compliance`

Auto-create recall/compliance evidence:

- Recall reports start as `needs_review`.
- Recall completion receipt starts as `completed` with remedy `completed`.
- Import/RIV/SOC documents start as compliance `needs_review` unless they are explicitly entered later as compliant.

## Reports

Extend decision reports with:

- `verification.recall` based on latest evidence and uploaded documents.
- `recall_compliance` section with latest evidence and full evidence list.
- Risk factors for open recalls, incomplete remedies, blocked import/compliance state, RIV inspection needs, and missing recall/compliance evidence when the blocker exists.
- HTML section titled `Recall and Compliance`.

## Dashboard

Add a recall/compliance control group on opportunity cards:

- Summary pill for latest status.
- Source/status/provider/reference/linked-document fields.
- Campaign/remedy/completion fields.
- Compliance/import/RIV/inspection fields.
- Notes field and save button.

## Tests

Add or update tests for:

- Alembic head creates the recall/compliance table and columns.
- Manual no-open-recalls/compliant evidence clears `recall_compliance` and updates reports.
- Open recall/remedy-required evidence keeps `recall_compliance` and adds report risk factors.
- Recall completion document upload auto-creates completed evidence.
- Dashboard assets expose recall/compliance controls.

## Verification

Run:

- `uv run pytest tests/test_previsit_persistence.py tests/test_migrations.py tests/test_dashboard.py`
- `uv run python -m compileall app`
- `uv run pytest`
- `uv run alembic upgrade head`
- Restart the local API server and verify OpenAPI/dashboard assets expose the new workflow.
