# PostgreSQL API Runtime Verification Plan

## Objective

Verify the real FastAPI search route persists and retrieves pre-visit analysis results against PostgreSQL, not only SQLite or a direct service-layer session.

## Scope

Implemented now:

- Refactor DB session creation so the current `DATABASE_URL` is respected at runtime.
- Add an optional Postgres integration test for `POST /api/searches/run`.
- Verify the route response returns a `run_id`.
- Verify `GET /api/searches/runs/{run_id}` returns persisted candidates.
- Verify rows exist in `search_runs` and `candidate_snapshots`.
- Add a Make target for API-level Postgres verification.

## Test Strategy

The route-level Postgres test is skipped by default. It runs only when `TEST_DATABASE_URL` starts with `postgresql`.

The test:

1. Resets the local Postgres `public` schema.
2. Runs `alembic upgrade head`.
3. Sets `DATABASE_URL` to the same Postgres URL.
4. Starts the FastAPI app in-process with `TestClient`.
5. Calls `POST /api/searches/run` with fixture scraping enabled.
6. Calls `GET /api/searches/runs/{run_id}`.
7. Checks database row counts directly.
8. Resets the schema after the test.

## Done Criteria

- Normal test suite still passes without Docker.
- `make postgres-api-test` passes against Docker Postgres.
- `make postgres-verify` includes migration, service-layer persistence, and API route persistence verification.
