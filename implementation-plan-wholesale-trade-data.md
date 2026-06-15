# Wholesale/Trade-In Data Implementation Plan

## Goal

Add wholesale and trade-in evidence support for opportunities so Canadian dealers can record Canadian Black Book, Manheim MMR, OPENLANE/ADESA/TradeRev auction activity, condition grade, bid activity, and a wholesale-supported buy calculation.

The first implementation is manual/document-backed and integration-ready. It does not scrape authenticated valuation or dealer-auction portals; it stores dealer-entered/exported evidence and uploaded reports consistently so paid APIs or partner feeds can be attached later.

## Current Gaps

- Pricing is retail-comparable driven only.
- There is no table for wholesale or trade-in valuation evidence.
- Auction condition reports can be uploaded, but they do not create structured auction/condition data.
- Decision reports do not show CBB/MMR/OPENLANE support, auction sale range, bid activity, condition grade, or wholesale support versus the retail-derived max buy.
- Dashboard opportunity cards do not expose wholesale evidence entry.

## Data Model

Create `opportunity_wholesale_evidence` with:

- Opportunity/document linkage: `opportunity_id`, optional `document_id`.
- Source fields: `source_type`, `provider`, `lookup_reference`, `checked_at`, `region`.
- Valuation fields: `wholesale_low_cad`, `wholesale_avg_cad`, `wholesale_high_cad`, `trade_in_value_cad`, `retail_value_cad`.
- Auction fields: `auction_sale_low_cad`, `auction_sale_avg_cad`, `auction_sale_high_cad`, `bid_count`, `bidder_count`, `high_bid_cad`, `sale_price_cad`, `reserve_price_cad`.
- Condition fields: `condition_grade`, `condition_score`, `condition_notes`.
- Cost/support fields: `buyer_fee_cad`, `transport_estimate_cad`, `reconditioning_estimate_cad`.
- Audit/details: `notes`, `raw_payload`, timestamps.

Allowed `source_type` values:

- `manual`
- `canadian_black_book`
- `manheim_mmr`
- `openlane`
- `adesa`
- `traderev`
- `auction_report`
- `trade_in_appraisal`
- `document_upload`

Allowed `condition_grade` values:

- `unknown`
- `rough`
- `average`
- `clean`
- `extra_clean`
- `auction_1`
- `auction_2`
- `auction_3`
- `auction_4`
- `auction_5`

## Wholesale Support Calculation

For each opportunity, compute a report-ready `wholesale_support` summary from the latest evidence:

- Representative wholesale value uses `wholesale_avg_cad`, then `trade_in_value_cad`, then `auction_sale_avg_cad`, then `high_bid_cad`, then `sale_price_cad`.
- Low/high support values use explicit low/high values when available, otherwise derive an 8% band around the representative value.
- Condition adjustment:
  - `extra_clean` / `auction_5`: +3%
  - `clean` / `auction_4`: +1%
  - `average` / `auction_3`: 0%
  - `rough` / `auction_1` / `auction_2`: -6%
- Supported max buy subtracts buyer fee, transport estimate, and reconditioning estimate from the adjusted representative value.
- Suggested opening bid is 96% of supported max buy.
- If the retail-derived `pricing.max_buy_price_cad` exceeds supported max buy, the report adds a risk factor.

## API

Add:

- `POST /api/opportunities/{opportunity_id}/wholesale-evidence`
- `GET /api/opportunities/{opportunity_id}/wholesale-evidence`

Extend opportunity payloads with:

- `wholesale_evidence.status`
- `wholesale_evidence.count`
- `wholesale_evidence.latest`
- `wholesale_evidence.support`
- `wholesale_evidence.evidence`

Extend document upload response with optional `wholesale_evidence` when a supported document type is uploaded.

## Document Upload Ingestion

Add document types:

- `cbb_valuation`
- `manheim_mmr`
- `openlane_auction_report`
- `adesa_auction_report`
- `traderev_bid_report`
- `trade_in_appraisal`
- `wholesale_invoice`

Auto-create wholesale evidence:

- CBB/MMR uploads start as their corresponding source type.
- OPENLANE/ADESA/TradeRev reports start as auction evidence.
- Existing `auction_condition_report` creates auction-report evidence with condition unknown.
- Trade-in appraisals create trade-in evidence.

## Reports

Extend decision reports with:

- `wholesale_evidence` section containing latest evidence, evidence list, and support calculation.
- Pricing section fields for wholesale support and suggested bid.
- Risk factors for stale/missing wholesale support where applicable, max-buy exceeding wholesale support, low bid activity, condition grade below average, and sale price above support.
- HTML section titled `Wholesale and Trade-In Evidence`.

## Dashboard

Add a wholesale evidence control group on opportunity cards:

- Summary pill for latest source/status.
- Source/provider/reference/linked-document fields.
- Wholesale low/avg/high and trade-in/retail values.
- Auction sale low/avg/high, bid count, high bid, sale price, reserve.
- Condition grade/score and support-cost fields.
- Notes field and save button.

## Tests

Add or update tests for:

- Alembic head creates the wholesale evidence table and columns.
- Manual CBB evidence produces a support calculation and report section.
- Manheim/Openlane auction evidence with low bid activity adds report risk factors.
- Auction/trade-in document upload auto-creates wholesale evidence.
- Dashboard assets expose wholesale controls.

## Verification

Run:

- `uv run pytest tests/test_previsit_persistence.py tests/test_migrations.py tests/test_dashboard.py`
- `uv run python -m compileall app`
- `uv run pytest`
- `uv run alembic upgrade head`
- Restart the local API server and verify OpenAPI/dashboard assets expose the new workflow.
