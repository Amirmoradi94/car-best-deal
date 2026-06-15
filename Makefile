POSTGRES_DATABASE_URL ?= postgresql+psycopg://car_dealer:car_dealer_password@localhost:55433/car_dealer

.PHONY: postgres-up postgres-down postgres-logs postgres-migrate postgres-test postgres-api-test postgres-verify api-postgres test

postgres-up:
	docker compose up -d postgres

postgres-down:
	docker compose down

postgres-logs:
	docker compose logs -f postgres

postgres-migrate:
	DATABASE_URL="$(POSTGRES_DATABASE_URL)" uv run alembic upgrade head

postgres-test:
	TEST_DATABASE_URL="$(POSTGRES_DATABASE_URL)" uv run --extra dev pytest tests/test_postgres_runtime.py

postgres-api-test:
	TEST_DATABASE_URL="$(POSTGRES_DATABASE_URL)" uv run --extra dev pytest tests/test_postgres_api_runtime.py

postgres-verify: postgres-up postgres-migrate postgres-test postgres-api-test

api-postgres:
	DATABASE_URL="$(POSTGRES_DATABASE_URL)" SCRAPING_FIXTURE_MODE=true uv run uvicorn app.api.main:app --reload

test:
	uv run --extra dev pytest
