# Implementation Plan: Search Relevance Filtering

## Objective

Prevent broad Kijiji results from ranking unrelated vehicles too highly.

Example problem:

- Dealer searches: `2020 Honda Civic Montreal`.
- Kijiji returns mixed vehicles such as Kia, Mazda, Volkswagen, and Honda.
- The pipeline currently ranks all parsed results against the same batch, even if they do not match the intended vehicle.

## Scope

This milestone includes:

- Inferring intended year/make/model from `SearchFilters`.
- Scoring every listing for search relevance.
- Filtering clearly off-query listings before pricing.
- Applying a deal-score penalty for borderline listings.
- Returning relevance metadata in API output.
- Tests for exact, partial, and off-query matches.

This milestone excludes:

- AI natural-language interpretation.
- Synonym dictionaries for every brand/model.
- Advanced trim equivalence.
- Multi-source relevance normalization.

## Relevance Rules

Initial score range:

- `0.0` to `1.0`

Signals:

- Make match.
- Model match.
- Year match or near-year match.
- Query token overlap with listing title/trim.

Default behavior:

- Filter out listings below `0.45`.
- Keep borderline listings between `0.45` and `0.70`, but penalize final deal score.
- Treat exact make/model matches as high relevance even if the model naming is imperfect.

## Done Criteria

- Live Kijiji search results are filtered to query-relevant opportunities.
- API output includes relevance score/reasons.
- Tests pass.

