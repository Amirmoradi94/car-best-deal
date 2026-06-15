# Implementation Plan: Pre-Visit Analysis Persistence

## Objective

Persist pre-visit search runs and enriched candidate results so dealers can review, compare, and audit previous opportunity decisions.

## Scope

This milestone includes:

- Portable SQLAlchemy JSON columns for local SQLite tests and future PostgreSQL.
- Database session/engine setup.
- `search_runs` table for each analysis execution.
- `candidate_snapshots` table for enriched ranked candidates.
- Persistence service for `ScoredOpportunity` results.
- API endpoints to run, list, and fetch persisted analyses.
- Tests for persistence and API response shape.

This milestone excludes:

- Alembic migrations.
- User authentication.
- Multi-dealer authorization rules.
- Updating old runs when source listings change.
- UI screens.

## Stored Search Run Data

- Search name / search ID
- Natural-language query
- Structured filters
- Listing limit
- Status
- Candidate count
- Error message if a run fails

## Stored Candidate Data

- Source name, source URL, listing ID
- Vehicle year/make/model/trim/VIN/mileage/body/drivetrain
- Price and location
- Deal score and recommendation
- Pricing summary
- Risk summary
- Relevance reasons
- Image URLs and image-risk reasons

## API Workflow

1. `POST /api/searches` creates a saved search definition.
2. `POST /api/searches/{search_id}/run` runs pre-visit analysis and persists a `search_run`.
3. `GET /api/searches/runs` lists recent runs.
4. `GET /api/searches/runs/{run_id}` returns run metadata and candidate summaries.
5. `GET /api/searches/runs/{run_id}/candidates/{candidate_id}` returns one full candidate snapshot.

## Done Criteria

- Running an analysis creates one search run and candidate rows.
- Run and candidate detail endpoints return stored data without rerunning scraping.
- Tests pass against SQLite in memory.
