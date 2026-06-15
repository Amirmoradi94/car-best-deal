import os

import pytest
from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.scraping.contracts import SearchFilters
from app.services.previsit_persistence import persist_search_run
from app.services.search_pipeline import SearchPipeline


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="Set TEST_DATABASE_URL to run Postgres runtime integration test.",
)
@pytest.mark.asyncio
async def test_postgres_migration_and_persistence_runtime(monkeypatch) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    engine = create_engine(database_url)
    _reset_public_schema(engine)

    try:
        upgrade(Config("alembic.ini"), "head")

        scored_items = await SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True)).run_previsit_candidate_search(
            SearchFilters(query="2020 Honda Civic Montreal", limit=25),
            max_candidates=2,
        )

        with Session(engine) as session:
            run = persist_search_run(
                session,
                search_id="postgres-runtime-search",
                name="Postgres runtime smoke",
                filters=SearchFilters(query="2020 Honda Civic Montreal", limit=25),
                scored_items=scored_items,
            )
            candidate_count = session.execute(
                text("select count(*) from candidate_snapshots where search_run_id = :run_id"),
                {"run_id": run.id},
            ).scalar_one()

        assert candidate_count == 2
    finally:
        _reset_public_schema(engine)
        engine.dispose()
        get_settings.cache_clear()


def _reset_public_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("drop schema if exists public cascade"))
        connection.execute(text("create schema public"))
