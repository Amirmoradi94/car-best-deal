# Implementation Plan: Gemini Image Risk Analyzer

## Objective

Replace the deterministic image-risk placeholder with a Gemini-backed analyzer for live pre-visit candidate review, while keeping fixtures and tests deterministic.

## API Basis

Use Google Gemini `models.generateContent` with multimodal image parts and JSON output. The default model is `gemini-3.5-flash`, configurable through environment variables.

## Scope

This milestone includes:

- Gemini environment configuration.
- Image fetch/cache layer for shortlisted candidate image URLs.
- Gemini image-analysis prompt and structured JSON contract.
- `GeminiImageRiskAnalyzer` behind the existing image-risk boundary.
- Deterministic fallback when Gemini is disabled, missing credentials, in fixture mode, or fails.
- Mocked tests for Gemini request/response handling.
- Documentation for required environment variables.

This milestone excludes:

- Persisting downloaded image bytes.
- Retrying multiple Gemini models.
- Streaming responses.
- Storing per-image explanations in a database.

## Runtime Rules

1. Run Gemini only after the discovery/ranking cap has selected final candidates.
2. Run Gemini only when:
   - `SCRAPING_FIXTURE_MODE=false`
   - `GEMINI_IMAGE_ANALYSIS_ENABLED=true`
   - `GEMINI_API_KEY` is present
3. Use deterministic analyzer everywhere else.
4. If image fetching or Gemini parsing fails, fall back to deterministic analysis for that listing.

## JSON Contract

Gemini should return:

```json
{
  "risk_adjustment": -8,
  "reasons": ["visible_body_damage", "missing_interior_photos"],
  "summary": "Short dealer-facing explanation.",
  "confidence": 0.74
}
```

`risk_adjustment` is clamped to `[-25, 8]`; negative values reduce the deal score and increase risk.

## Done Criteria

- Gemini analyzer builds valid multimodal requests.
- Tests verify request construction and JSON parsing with mocked HTTP responses.
- Pipeline selects Gemini only for configured live mode.
- Full test suite passes without requiring network or credentials.
