# Implementation Plan: Natural-Language Search Interpretation

## Objective

Convert natural-language dealer search text into structured search filters and show the interpreted filters before running the search.

## Current State

- The search API accepts `natural_language_query`.
- The dashboard has a natural query input.
- Search execution currently builds `SearchFilters` from structured form fields only.
- Relevance scoring reads the query later, but source adapters and normalized filters do not get a structured interpretation.
- The dashboard does not preview what the query means before search.

## Scope

1. Add a deterministic natural-language interpreter.
2. Add a preview endpoint: `POST /api/searches/interpret`.
3. Merge interpreted filters with explicit structured filters.
4. Use the same merge during actual search execution.
5. Return interpreted/applied filters in run responses.
6. Add dashboard preview controls.
7. Add regression tests and docs.

## Interpretation Rules

The MVP parser supports common dealer search wording:

- Years:
  - `2020 Honda Civic`
  - `2018-2021 Toyota Corolla`
  - `2019 or newer`
  - `2021 or older`
- Price:
  - `under $20k`
  - `below 25000`
  - `over $10000`
- Mileage:
  - `under 100k km`
  - `less than 120000 km`
- Seller:
  - `private seller`
  - `dealer`
- Location:
  - common city/province names and Canadian province abbreviations
- Vehicle identity:
  - make/model from a curated map for common Canadian-market vehicles

Explicit form fields always win over interpreted fields. Interpreted values fill blanks only.

## API

`POST /api/searches/interpret`

Request:

```json
{
  "natural_language_query": "2020 Honda Civic under $20k Montreal private seller",
  "structured_filters": {}
}
```

Response:

```json
{
  "natural_language_query": "...",
  "interpreted_filters": {},
  "applied_filters": {},
  "interpretation": {
    "confidence": 0.8,
    "notes": []
  }
}
```

## Execution

Search execution calls the interpreter before constructing `SearchFilters`. The merged filters are persisted in search-run normalized filters, so the run history reflects what actually executed.

## Dashboard

Add an `Interpret` button beside search actions and a compact preview panel showing applied make/model/year/price/mileage/location/seller filters. Running a search refreshes this preview with the filters actually used.

## Verification

- Parser extracts year, make, model, price, mileage, seller, and location.
- Preview endpoint returns interpreted and applied filters.
- Natural-only search runs use interpreted filters.
- Saved natural-only searches rerun with interpreted filters.
- Dashboard serves interpretation controls.
- Full test suite passes.
