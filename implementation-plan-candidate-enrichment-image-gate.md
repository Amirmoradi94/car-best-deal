# Implementation Plan: Candidate Detail Enrichment and Image Gate

## Objective

Add the pre-visit candidate enrichment stage that runs after discovery ranking. The app should enrich only the best candidates, then apply image-risk signals before returning a dealer-facing shortlist.

## Scope

This milestone includes:

- A top-candidate cap with a default maximum of 50.
- Detail-page fetching for shortlisted candidates.
- Merging enriched detail fields back into listing snapshots.
- Carrying listing image URLs into the domain model.
- A deterministic image-risk analyzer that acts as the Gemini integration boundary.
- Re-scoring enriched candidates with image-risk adjustments.
- Tests for enrichment cap, detail merge, and image-risk scoring.

This milestone excludes:

- Live Gemini API calls.
- Downloading image bytes.
- Storing per-image model explanations in a database.
- User-facing report templates.

## Workflow

1. Run existing multi-source discovery and ranking.
2. Select the top ranked candidates up to `DealerSettings.max_candidate_count`.
3. Fetch each candidate detail page from the source adapter.
4. Parse the detail page into a normalized `ParsedListing`.
5. Merge enriched fields into the original `ListingSnapshot`, preserving the original listing ID and ranking context.
6. Run image risk only for enriched candidates.
7. Recalculate risk, pricing, and deal score with the enriched listing.
8. Return the enriched, re-ranked pre-visit shortlist.

## Image Risk Boundary

The deterministic analyzer returns:

- `risk_adjustment`: score adjustment applied to the listing.
- `reasons`: compact machine-readable reason codes.
- `image_count`: number of available images considered.

Gemini can later replace this analyzer behind the same service boundary. The prompt should evaluate exterior damage, mismatched panels, tire/wheel condition, interior wear, dashboard warning lights, photo quality, and missing critical angles.

## Done Criteria

- Enrichment fetches detail pages only for capped top candidates.
- Enriched candidates include image URLs.
- Image-risk output affects risk and deal score.
- Existing batch ranking still works.
- Tests pass.
