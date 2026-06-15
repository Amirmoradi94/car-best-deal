# PostgreSQL Local Runtime Plan

## Objective

Add a repeatable local PostgreSQL runtime so migrations and persistence can be verified against the same database family intended for production.

## Scope

Implemented now:

- Docker Compose service for PostgreSQL.
- Postgres-specific env example with the app `DATABASE_URL`.
- Make targets for starting/stopping Postgres, running migrations, running the API against Postgres, and running optional Postgres tests.
- Optional integration test that runs only when `TEST_DATABASE_URL` is set to a PostgreSQL URL.
- Docs for SQLite versus PostgreSQL workflows.

## Local Workflow

1. Start Postgres with Docker Compose.
2. Run Alembic migrations against the Postgres URL.
3. Run the API with `DATABASE_URL` pointing at Postgres.
4. Optionally run the Postgres integration test.

## Validation Criteria

- `uv run --extra dev pytest` still passes without Docker.
- `uv run alembic upgrade head` still works for SQLite.
- When Docker is available, `make postgres-verify` upgrades Postgres and verifies persistence into `search_runs` and `candidate_snapshots`.

## Deferred

- Production Docker image for the API.
- Hosted Postgres provisioning.
- Removing runtime `init_db()` fallback from the API startup path.
