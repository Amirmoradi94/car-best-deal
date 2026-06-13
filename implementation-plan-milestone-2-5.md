# Implementation Plan: Milestone 2.5

## Objective

Make the scraping layer production-shaped before adding more marketplace sources.

This milestone adds the infrastructure needed to safely collect, store, inspect, and convert scraped source data into reusable fixtures and later database records.

## Scope

Milestone 2.5 includes:

- Local object storage abstraction.
- Source snapshot persistence service.
- Standard source failure taxonomy.
- Kijiji search snapshot fetch hook.
- Kijiji live Zyte smoke CLI.
- Fixture-save workflow for live HTML.
- Tests for local storage, snapshot persistence, failure objects, and adapter search snapshot behavior.

Milestone 2.5 excludes:

- Production object storage such as S3/R2/GCS.
- Real database session persistence.
- Full live Kijiji selector hardening.
- AutoTrader adapter.
- Gemini fallback extraction.
- Scheduled worker execution.

## Build Sequence

### Step 1: Storage Abstraction

Create:

- `ObjectStore` protocol.
- `StoredObject` metadata object.
- `LocalObjectStore` implementation.

The local store should:

- Write bytes and text.
- Read bytes and text.
- Generate stable object keys.
- Prevent path traversal.
- Store files under `var/object-store` by default.

### Step 2: Source Snapshot Persistence

Create a service that accepts a `SourceSnapshot` and persists:

- HTML.
- Screenshot if present.
- Metadata JSON.

The service returns a persisted snapshot descriptor with:

- Source name.
- Source URL.
- HTML object key.
- Screenshot object key if present.
- Metadata object key.
- Expiry timestamp.

Raw source retention default:

- 90 days.

### Step 3: Source Failure Taxonomy

Create standard source failure reasons:

- blocked.
- timeout.
- parsing_failed.
- no_results.
- source_layout_changed.
- source_unavailable.
- credentials_missing.
- unknown.

These should be reusable by every future source adapter.

### Step 4: Kijiji Snapshot Hook

Add:

- `fetch_search_snapshot(filters)`.

This allows search raw HTML to be saved before result refs are parsed.

### Step 5: Live Zyte Smoke CLI

Create:

```bash
uv run python -m app.cli.scrape_kijiji "2020 Honda Civic Montreal"
```

Behavior:

- Requires `ZYTE_API_KEY` unless fixture mode is explicitly used.
- Fetches a Kijiji search page through Zyte.
- Saves raw search snapshot locally.
- Parses listing refs.
- Optionally fetches the first listing page.
- Optionally saves search/listing HTML into fixture paths.

### Step 6: Tests

Add tests for:

- Local object store write/read.
- Source snapshot persistence.
- Source failure representation.
- Kijiji search snapshot in fixture mode.

## Done Criteria

Milestone 2.5 is complete when:

- Tests pass.
- Raw source snapshots can be persisted locally.
- Kijiji adapter can return a search `SourceSnapshot`.
- CLI imports and has a safe no-credentials failure path.
- The fixture-save workflow is available for live Zyte output.

