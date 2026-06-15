# AI Output Audit Trail Implementation Plan

## Problem

The app can use deterministic local AI-style extractors and Gemini-backed analysis for listing fallback extraction, risk-language detection, comparable relevance, vehicle-history text extraction, and report narrative writing. A first-pass `ai_model_outputs` table exists, but it only stores the model string, raw parsed output, aggregate confidence, and object-store keys. It does not provide enough audit detail for AI-derived data:

- model name and model version are not stored separately
- parsed output is not persisted as a schema-validated record
- confidence is not available per AI-derived field
- source-evidence links are not normalized or carried in compact references

## Scope

1. Upgrade `ai_model_outputs` persistence without removing existing columns.
2. Add validation metadata and validated output payloads for every AI extraction feature.
3. Add per-field confidence maps for every AI extraction feature.
4. Add source-evidence link payloads for every AI extraction feature.
5. Include the new audit metadata in compact AI references used by candidates, history ingestion, and decision reports.
6. Keep deterministic fixture/local flows working so tests do not require external AI credentials.

## Data Model

Extend `ai_model_outputs` with:

- `model_version`: explicit deployed model/version identifier. For Gemini this will mirror the configured model unless a provider-specific version is later available. For local deterministic extraction it will be `local-rules-v1`.
- `schema_name`: stable schema name for the feature output.
- `schema_version`: integer schema version.
- `validated_output`: schema-normalized JSON object used by downstream audit/review.
- `field_confidences`: JSON object keyed by output field name, with numeric confidence values in `[0, 1]`.
- `evidence_links`: JSON list of source-evidence objects. Each evidence object will include a source type plus enough linkage to retrieve or identify the evidence, such as source URL, subject ID, parser confidence, object-store key, text excerpt hash, or document/report IDs.

Keep existing `parsed_output`, `confidence`, `input_object_key`, and `output_object_key` for compatibility.

## Service Design

Create schema specs in `app/services/ai_extraction.py` using local Pydantic models:

- `listing_extraction_fallback`
- `risk_language_detection`
- `vehicle_history_extraction`
- `comparable_relevance_ai`
- `report_writing`

Each schema spec provides:

- schema name and version
- Pydantic model for validation and normalization
- field-confidence extraction rules
- source-evidence extraction rules

`AIExtractionService._record()` will:

1. determine provider, model, and model version
2. validate raw parsed output with the feature schema
3. derive `validated_output`
4. derive per-field confidences
5. derive source-evidence links from the input payload and subject metadata
6. write both raw and validated output to object storage
7. insert the enriched `AIModelOutput` row
8. return a compact reference with the audit metadata needed by API payloads and reports

If validation fails, the deterministic fallback output should still be normalized by the same schema. Unexpected invalid provider output should be treated as a failed provider result and fall back to deterministic extraction.

## API and Report Exposure

The current app already exposes compact `ai_outputs` references in:

- search candidate payloads
- persisted candidate snapshots
- opportunity history ingestion response
- decision report evidence

Those references will include:

- `schema_name`
- `schema_version`
- `model_version`
- `field_confidences`
- `evidence_links`

This avoids adding a new endpoint in this slice while making every AI-derived field traceable from existing user-facing payloads. A future UI can expand an audit reference into a full audit viewer.

## Tests

1. Migration smoke test verifies all new columns on `ai_model_outputs`.
2. Search/persistence test verifies AI output rows include schema metadata, validated output, per-field confidence, evidence links, model version, and object-store output JSON.
3. Candidate payload test verifies compact `ai_outputs` references expose field confidences and evidence links.
4. Vehicle-history extraction test verifies history `raw_payload.ai_extraction` carries the new audit metadata and the DB row stores the normalized history output.
5. Decision-report narrative test verifies report evidence includes the enriched `report_writing` audit reference.

## Acceptance Criteria

- Every AI-derived output has a persisted audit row with model, model version, schema name/version, validated output, per-field confidence, and evidence links.
- Existing deterministic test mode remains offline and repeatable.
- Existing candidate/history/report payloads carry enough audit metadata to trace AI-derived fields without fetching raw object-store files.
- Relevant tests and migration smoke checks pass.
