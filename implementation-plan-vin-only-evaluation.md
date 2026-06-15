# VIN-Only Evaluation Implementation Plan

## Objective

Replace the current `501` VIN-only blocker with a usable first slice of VIN evaluation.

The goal is not to pretend paid history, lien, recall, or VIN-provider integrations exist. The goal is to let a dealer enter a VIN, get a validated/decoded vehicle identity seed, search marketplace sources for comparable/source matches, create an opportunity, and generate a report that clearly marks history, lien, and recall checks as unresolved.

## Scope

Implement:

- VIN normalization and validation.
- Basic VIN decode for model year, WMI/manufacturer, and country.
- VIN-only search run support through `/api/searches/run`.
- Saved VIN-only search support.
- Direct VIN promotion through `/api/opportunities/from-vin`.
- Source-status diagnostics for:
  - VIN decode.
  - VIN source matching.
  - Vehicle history check placeholder.
  - Lien/title check placeholder.
  - Recall check placeholder.
- Report JSON verification section for VIN/history/lien/recall status.
- Tests for valid VIN-only search, direct VIN opportunity/report generation, saved VIN search, and invalid VIN rejection.

## Design Choices

- Use deterministic local VIN validation only. No paid report purchase or external VIN decode API.
- Use decoded make/year when available; use user-provided structured filters for model/trim/location.
- Score a synthetic VIN target against marketplace comparables so pricing can still be preliminary.
- Mark history/lien/recall checks as `not_configured` until real integrations or document uploads exist.

## Acceptance Criteria

- VIN-only requests no longer return `501`.
- Invalid VINs return `400`.
- A valid VIN can produce a persisted run and candidate.
- A valid VIN can be promoted to an opportunity through `/api/opportunities/from-vin`.
- A report generated from that opportunity includes `evidence.intake_mode: "vin"` and unresolved verification statuses.
- Full test suite passes.
