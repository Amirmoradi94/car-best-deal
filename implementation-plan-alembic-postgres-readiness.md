# Alembic and PostgreSQL Readiness Plan

## Objective

Move schema changes out of ad-hoc `Base.metadata.create_all()` and into versioned Alembic migrations, while keeping SQLite usable for local MVP development and tests.

## Current State

- Runtime default database is SQLite: `sqlite:///var/car-dealer.db`.
- SQLAlchemy models are PostgreSQL-compatible.
- JSON fields use SQLite `JSON` locally and PostgreSQL `JSONB` through a SQLAlchemy type variant.
- The app still has a local `init_db()` helper for lightweight test/dev setup.

## Implementation Scope

1. Add Alembic dependency.
2. Add `alembic.ini`.
3. Add `alembic/env.py` wired to:
   - `app.core.config.get_settings()`
   - `app.db.base.Base.metadata`
   - `app.db.models` imports so all tables are registered.
4. Generate an initial migration for the current schema.
5. Add a migration smoke test that upgrades an empty SQLite database to `head`.
6. Update docs with:
   - SQLite migration command.
   - PostgreSQL `DATABASE_URL` example.
   - Guidance that deploys should run migrations instead of relying on `create_all()`.

## Runtime Decision

For this MVP, keep `init_db()` available because existing tests and local API runs use it. Production/deploy flows should use Alembic migrations. In a later deployment milestone, app startup should stop auto-creating tables and fail fast if migrations have not been applied.

## Done Criteria

- `uv run alembic upgrade head` works against SQLite.
- Tests can run migration upgrade against a temporary SQLite database.
- Existing backend test suite still passes.
- Docs clearly state how SQLite and future PostgreSQL are handled.
