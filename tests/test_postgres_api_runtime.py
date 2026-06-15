import os

import pytest
from alembic.command import upgrade
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api.main import create_app
from app.core.config import get_settings
from app.db.session import clear_session_cache


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="Set TEST_DATABASE_URL to run Postgres API runtime integration test.",
)
def test_postgres_api_search_run_persists_and_reads_back(monkeypatch) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SCRAPING_FIXTURE_MODE", "true")
    get_settings.cache_clear()
    clear_session_cache()

    engine = create_engine(database_url)
    _reset_public_schema(engine)

    try:
        upgrade(Config("alembic.ini"), "head")

        client = TestClient(create_app())
        response = client.post(
            "/api/searches/run",
            json={
                "name": "Postgres API runtime smoke",
                "natural_language_query": "2020 Honda Civic Montreal",
                "listing_limit": 25,
                "sources": "both",
                "max_candidates": 2,
            },
        )

        assert response.status_code == 200
        body = response.json()
        run_id = body["run_id"]
        assert run_id
        assert len(body["ranked_opportunities"]) == 2

        run_response = client.get(f"/api/searches/runs/{run_id}")
        assert run_response.status_code == 200
        run_body = run_response.json()
        assert run_body["id"] == run_id
        assert run_body["candidate_count"] == 2
        assert len(run_body["ranked_opportunities"]) == 2

        with engine.connect() as connection:
            search_run_count = connection.execute(
                text("select count(*) from search_runs where id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()
            candidate_count = connection.execute(
                text("select count(*) from candidate_snapshots where search_run_id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()

        assert search_run_count == 1
        assert candidate_count == 2
    finally:
        _reset_public_schema(engine)
        engine.dispose()
        get_settings.cache_clear()
        clear_session_cache()


def _reset_public_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("drop schema if exists public cascade"))
        connection.execute(text("create schema public"))
