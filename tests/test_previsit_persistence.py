from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import create_app
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import DealerSettingsModel, Search
from app.db.session import get_session
from app.scraping.contracts import SearchFilters
from app.services.previsit_persistence import (
    get_candidate_snapshot,
    get_search_run_with_candidates,
    list_search_runs,
    persist_search_run,
)
from app.services.scheduled_search_refresh import (
    execute_scheduled_saved_search_refresh,
    is_saved_search_due,
)
from app.services.search_pipeline import SearchPipeline


@pytest.mark.asyncio
async def test_persist_search_run_stores_ranked_candidate_snapshots() -> None:
    scored_items = await SearchPipeline(Settings(SCRAPING_FIXTURE_MODE=True)).run_previsit_candidate_search(
        SearchFilters(query="2020 Honda Civic Montreal", limit=25),
        max_candidates=2,
    )
    engine = _memory_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        run = persist_search_run(
            session,
            search_id="search-001",
            name="Honda Civic shortlist",
            filters=SearchFilters(query="2020 Honda Civic Montreal", limit=25),
            scored_items=scored_items,
        )

        persisted = get_search_run_with_candidates(session, run.id)
        assert persisted is not None
        saved_run, candidates = persisted
        assert saved_run.candidate_count == 2
        assert candidates[0].rank == 1
        assert candidates[0].listing_id == scored_items[0].listing.id
        assert candidates[0].image_urls
        assert candidates[0].image_risk_reasons == ["too_few_listing_images"]
        assert candidates[0].selected is False
        assert candidates[0].hidden is False
        assert candidates[0].seller_contact_status is None
        assert candidates[0].seller_notes is None
        assert list_search_runs(session)[0].id == run.id


def test_search_run_api_persists_and_returns_candidate_detail() -> None:
    client = _test_client()
    create_response = client.post(
        "/api/searches",
        json={
            "name": "Honda Civic saved search",
            "natural_language_query": "2020 Honda Civic Montreal",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "year_min": 2020,
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "both",
            "max_candidates": 2,
        },
    )
    assert create_response.status_code == 200
    search_id = create_response.json()["id"]

    response = client.post(f"/api/searches/{search_id}/run")

    assert response.status_code == 200
    body = response.json()
    run_id = body["run_id"]
    assert run_id
    assert body["search_id"] == search_id
    assert body["ranked_opportunities"]
    assert {status["source_name"] for status in body["source_statuses"]} == {"kijiji", "autotrader"}
    assert all(status["status"] == "ok" for status in body["source_statuses"])

    run_response = client.get(f"/api/searches/runs/{run_id}")
    assert run_response.status_code == 200
    run_body = run_response.json()
    assert run_body["candidate_count"] == len(run_body["ranked_opportunities"])
    assert run_body["ranked_opportunities"][0]["image_count"] > 0
    assert run_body["source_statuses"] == body["source_statuses"]

    candidate_id = run_body["ranked_opportunities"][0]["id"]
    candidate_response = client.get(f"/api/searches/runs/{run_id}/candidates/{candidate_id}")
    assert candidate_response.status_code == 200
    assert candidate_response.json()["id"] == candidate_id
    assert candidate_response.json()["selected"] is False
    assert candidate_response.json()["hidden"] is False

    saved_search_response = client.get(f"/api/searches/{search_id}")
    assert saved_search_response.status_code == 200
    assert saved_search_response.json()["last_run_at"] is not None


def test_saved_search_api_persists_lists_and_returns_detail() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches",
        json={
            "name": "AutoTrader Civic saved search",
            "natural_language_query": "2020 Honda Civic Montreal",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "year_min": 2020,
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    search_id = body["id"]
    assert body["status"] == "created"
    assert body["sources"] == "autotrader"
    assert body["max_candidates"] == 3
    assert body["structured_filters"]["make"] == "Honda"

    list_response = client.get("/api/searches")
    assert list_response.status_code == 200
    searches = list_response.json()["searches"]
    assert [search["id"] for search in searches] == [search_id]

    detail_response = client.get(f"/api/searches/{search_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["name"] == "AutoTrader Civic saved search"
    assert detail["sources"] == "autotrader"
    assert detail["last_run_at"] is None


def test_saved_search_api_persists_and_updates_schedule() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches",
        json={
            "name": "Scheduled Civic monitor",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "sources": "autotrader",
            "scheduled": True,
            "schedule_cron": "every:30minutes",
        },
    )

    assert response.status_code == 200
    body = response.json()
    search_id = body["id"]
    assert body["scheduled"] is True
    assert body["schedule_cron"] == "every:30minutes"

    update_response = client.patch(
        f"/api/searches/{search_id}",
        json={"scheduled": True, "schedule_cron": "daily"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["scheduled"] is True
    assert update_response.json()["schedule_cron"] == "daily"

    invalid_response = client.patch(
        f"/api/searches/{search_id}",
        json={"scheduled": True, "schedule_cron": "nonsense"},
    )

    assert invalid_response.status_code == 422


def test_saved_search_alerts_generate_in_app_and_email_dry_run_alerts() -> None:
    client = _test_client()

    create_response = client.post(
        "/api/searches",
        json={
            "name": "Alerted AutoTrader monitor",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "year_min": 2020,
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 1,
            "alerts_enabled": True,
            "in_app_alerts_enabled": True,
            "email_alerts_enabled": True,
        },
    )
    assert create_response.status_code == 200
    search_id = create_response.json()["id"]
    with client.testing_session() as session:
        search = session.get(Search, search_id)
        session.add(
            DealerSettingsModel(
                dealer_account_id=search.dealer_account_id,
                candidate_score_threshold=1,
            )
        )
        session.commit()

    run_response = client.post(f"/api/searches/{search_id}/run")

    assert run_response.status_code == 200
    alerts_response = client.get("/api/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()["alerts"]
    high_score_alerts = [alert for alert in alerts if alert["alert_type"] == "high_score"]
    assert {alert["channel"] for alert in high_score_alerts} == {"in_app", "email"}
    in_app_alert = next(alert for alert in high_score_alerts if alert["channel"] == "in_app")
    email_alert = next(alert for alert in high_score_alerts if alert["channel"] == "email")
    assert in_app_alert["status"] == "unread"
    assert email_alert["status"] == "skipped"
    assert email_alert["metadata"]["email_delivery"] == "dry_run"

    read_response = client.patch(f"/api/alerts/{in_app_alert['id']}/read")

    assert read_response.status_code == 200
    assert read_response.json()["status"] == "read"
    assert read_response.json()["read_at"] is not None


def test_saved_search_alerts_detect_price_drop_against_previous_candidate() -> None:
    client = _test_client()

    create_response = client.post(
        "/api/searches",
        json={
            "name": "Price drop monitor",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "year_min": 2020,
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 1,
            "alerts_enabled": True,
            "in_app_alerts_enabled": True,
        },
    )
    search_id = create_response.json()["id"]

    first_run_response = client.post(f"/api/searches/{search_id}/run")
    first_run_id = first_run_response.json()["run_id"]
    first_candidate = client.get(f"/api/searches/runs/{first_run_id}").json()["ranked_opportunities"][0]
    client.patch(
        f"/api/searches/runs/{first_run_id}/candidates/{first_candidate['id']}",
        json={"seller_notes": "Keep previous candidate row for price-drop comparison."},
    )

    # Raise the previous snapshot price so the next fixture run is a detected drop.
    with client.testing_session() as session:
        candidate = get_candidate_snapshot(session, run_id=first_run_id, candidate_id=first_candidate["id"])
        candidate.asking_price_cad = (candidate.asking_price_cad or 0) + 5000
        session.add(candidate)
        session.commit()

    second_run_response = client.post(f"/api/searches/{search_id}/run")

    assert second_run_response.status_code == 200
    alerts = client.get("/api/alerts").json()["alerts"]
    price_drop_alert = next(alert for alert in alerts if alert["alert_type"] == "price_drop")
    assert price_drop_alert["channel"] == "in_app"
    assert price_drop_alert["status"] == "unread"
    assert price_drop_alert["metadata"]["old_price_cad"] > price_drop_alert["metadata"]["new_price_cad"]


def test_saved_search_run_without_body_uses_persisted_definition() -> None:
    client = _test_client()

    create_response = client.post(
        "/api/searches",
        json={
            "name": "AutoTrader rerun",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "year_min": 2020,
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 2,
        },
    )
    search_id = create_response.json()["id"]

    run_response = client.post(f"/api/searches/{search_id}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["search_id"] == search_id
    assert body["sources"] == ["autotrader"]
    assert len(body["ranked_opportunities"]) == 2
    assert {item["source"] for item in body["ranked_opportunities"]} == {"autotrader"}

    detail_response = client.get(f"/api/searches/{search_id}")
    assert detail_response.json()["last_run_at"] is not None


@pytest.mark.asyncio
async def test_scheduled_saved_search_refresh_runs_due_search_and_skips_recent_search() -> None:
    engine = _memory_engine()
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

    with testing_session() as session:
        due_response_search = client_payload = {
            "name": "Due AutoTrader monitor",
            "natural_language_query": "2020 Honda Civic Montreal",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 1,
            "scheduled": True,
            "schedule_cron": "every:30minutes",
        }
        recent_response_search = {
            **client_payload,
            "name": "Recent AutoTrader monitor",
            "schedule_cron": "daily",
        }
        from app.services.saved_searches import create_saved_search

        due_search = create_saved_search(
            session,
            name=due_response_search["name"],
            natural_language_query=due_response_search["natural_language_query"],
            structured_filters=due_response_search["structured_filters"],
            listing_limit=due_response_search["listing_limit"],
            sources=due_response_search["sources"],
            max_candidates=due_response_search["max_candidates"],
            scheduled=due_response_search["scheduled"],
            schedule_cron=due_response_search["schedule_cron"],
        )
        recent_search = create_saved_search(
            session,
            name=recent_response_search["name"],
            natural_language_query=recent_response_search["natural_language_query"],
            structured_filters=recent_response_search["structured_filters"],
            listing_limit=recent_response_search["listing_limit"],
            sources=recent_response_search["sources"],
            max_candidates=recent_response_search["max_candidates"],
            scheduled=recent_response_search["scheduled"],
            schedule_cron=recent_response_search["schedule_cron"],
        )
        recent_search.last_run_at = now - timedelta(hours=1)
        session.add(recent_search)
        session.commit()

        assert is_saved_search_due(due_search, now=now) is True
        assert is_saved_search_due(recent_search, now=now) is False

        summary = await execute_scheduled_saved_search_refresh(
            session,
            settings=Settings(SCRAPING_FIXTURE_MODE=True),
            now=now,
        )

        assert summary.due_count == 1
        assert summary.refreshed_count == 1
        assert summary.failed_count == 0
        assert summary.items[0].search_id == due_search.id
        assert summary.items[0].run_id

        runs = list_search_runs(session)
        assert len(runs) == 1
        assert runs[0].search_id == due_search.id
        session.refresh(due_search)
        assert due_search.last_run_at is not None


def test_candidate_workflow_state_api_updates_and_persists_candidate() -> None:
    client = _test_client()
    run_response = client.post(
        "/api/searches/run",
        json={
            "name": "Candidate workflow run",
            "natural_language_query": "2020 Honda Civic Montreal",
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 2,
        },
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    run_detail = client.get(f"/api/searches/runs/{run_id}").json()
    candidate_id = run_detail["ranked_opportunities"][0]["id"]

    update_response = client.patch(
        f"/api/searches/runs/{run_id}/candidates/{candidate_id}",
        json={
            "selected": True,
            "hidden": True,
            "seller_contact_status": "contacted",
            "seller_notes": "Ask for VIN photo and service records.",
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["selected"] is True
    assert updated["hidden"] is True
    assert updated["seller_contact_status"] == "contacted"
    assert updated["seller_notes"] == "Ask for VIN photo and service records."

    candidate_response = client.get(f"/api/searches/runs/{run_id}/candidates/{candidate_id}")
    assert candidate_response.json()["selected"] is True
    assert candidate_response.json()["hidden"] is True

    run_response = client.get(f"/api/searches/runs/{run_id}")
    persisted_candidate = run_response.json()["ranked_opportunities"][0]
    assert persisted_candidate["selected"] is True
    assert persisted_candidate["hidden"] is True


def test_candidate_workflow_state_api_allows_clearing_notes() -> None:
    client = _test_client()
    run_response = client.post(
        "/api/searches/run",
        json={
            "name": "Candidate note clearing",
            "natural_language_query": "2020 Honda Civic Montreal",
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 1,
        },
    )
    run_id = run_response.json()["run_id"]
    candidate_id = client.get(f"/api/searches/runs/{run_id}").json()["ranked_opportunities"][0]["id"]

    client.patch(
        f"/api/searches/runs/{run_id}/candidates/{candidate_id}",
        json={"seller_notes": "Temporary note", "seller_contact_status": "contacted"},
    )
    clear_response = client.patch(
        f"/api/searches/runs/{run_id}/candidates/{candidate_id}",
        json={"seller_notes": None, "seller_contact_status": None},
    )

    assert clear_response.status_code == 200
    assert clear_response.json()["seller_notes"] is None
    assert clear_response.json()["seller_contact_status"] is None


def test_candidate_workflow_state_api_returns_404_for_unknown_candidate() -> None:
    client = _test_client()

    response = client.patch(
        "/api/searches/runs/missing-run/candidates/missing-candidate",
        json={"selected": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate snapshot not found"


def test_candidate_promotion_creates_db_backed_opportunity_and_is_idempotent() -> None:
    client = _test_client()
    run_response = client.post(
        "/api/searches/run",
        json={
            "name": "Promotion run",
            "natural_language_query": "2020 Honda Civic Montreal",
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 1,
        },
    )
    run_id = run_response.json()["run_id"]
    candidate_id = client.get(f"/api/searches/runs/{run_id}").json()["ranked_opportunities"][0]["id"]
    client.patch(
        f"/api/searches/runs/{run_id}/candidates/{candidate_id}",
        json={
            "selected": True,
            "seller_contact_status": "contacted",
            "seller_notes": "Seller has service records.",
        },
    )

    promote_response = client.post(f"/api/searches/runs/{run_id}/candidates/{candidate_id}/promote")

    assert promote_response.status_code == 200
    opportunity = promote_response.json()
    opportunity_id = opportunity["id"]
    assert opportunity["stage"] == "candidate"
    assert opportunity["candidate_selected"] is True
    assert opportunity["seller_contact_status"] == "contacted"
    assert opportunity["seller_notes"] == "Seller has service records."
    assert opportunity["candidate"]["id"] == candidate_id
    assert opportunity["candidate"]["opportunity_id"] == opportunity_id

    second_promote_response = client.post(f"/api/searches/runs/{run_id}/candidates/{candidate_id}/promote")
    assert second_promote_response.status_code == 200
    assert second_promote_response.json()["id"] == opportunity_id

    candidate_response = client.get(f"/api/searches/runs/{run_id}/candidates/{candidate_id}")
    assert candidate_response.json()["opportunity_id"] == opportunity_id
    assert candidate_response.json()["selected"] is True

    list_response = client.get("/api/opportunities")
    assert list_response.status_code == 200
    opportunities = list_response.json()["opportunities"]
    assert [item["id"] for item in opportunities] == [opportunity_id]

    detail_response = client.get(f"/api/opportunities/{opportunity_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == opportunity_id
    assert detail["candidate"]["id"] == candidate_id
    assert detail["candidate"]["source"] == "autotrader"


def test_candidate_promotion_returns_404_for_unknown_candidate() -> None:
    client = _test_client()

    response = client.post("/api/searches/runs/missing-run/candidates/missing-candidate/promote")

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate snapshot not found"


def test_opportunity_stage_and_contact_updates_persist() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Stage workflow run")
    opportunity_id = opportunity["id"]

    stage_response = client.patch(
        f"/api/opportunities/{opportunity_id}/stage",
        json={"stage": "contact_seller"},
    )

    assert stage_response.status_code == 200
    assert stage_response.json()["stage"] == "contact_seller"

    contact_response = client.patch(
        f"/api/opportunities/{opportunity_id}/contact",
        json={
            "seller_contact_status": "appointment_set",
            "seller_notes": "Seller can meet Saturday morning.",
        },
    )

    assert contact_response.status_code == 200
    updated = contact_response.json()
    assert updated["seller_contact_status"] == "appointment_set"
    assert updated["seller_notes"] == "Seller can meet Saturday morning."

    detail_response = client.get(f"/api/opportunities/{opportunity_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["stage"] == "contact_seller"
    assert detail["seller_contact_status"] == "appointment_set"
    assert detail["candidate"]["seller_contact_status"] == "appointment_set"


def test_opportunity_ready_to_visit_requires_override_when_key_data_is_missing() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Ready guard run")
    opportunity_id = opportunity["id"]
    assert opportunity["missing_key_data"]
    assert opportunity["ready_to_visit_blocked"] is True
    assert opportunity["readiness_warnings"][0]["code"] == "missing_key_data"

    blocked_response = client.patch(
        f"/api/opportunities/{opportunity_id}/stage",
        json={"stage": "ready_to_visit"},
    )

    assert blocked_response.status_code == 200
    blocked = blocked_response.json()
    assert blocked["stage"] == "needs_data"
    assert blocked["stage_update_warning"] == "missing_key_data_requires_override"
    assert blocked["ready_to_visit_blocked"] is True

    override_response = client.patch(
        f"/api/opportunities/{opportunity_id}/stage",
        json={"stage": "ready_to_visit", "override_missing_data_warning": True},
    )

    assert override_response.status_code == 200
    overridden = override_response.json()
    assert overridden["stage"] == "ready_to_visit"
    assert overridden["ready_to_visit_blocked"] is False
    assert overridden["readiness_warnings"][0]["code"] == "missing_key_data"


def test_opportunity_stage_update_rejects_invalid_stage() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Invalid stage run")

    response = client.patch(
        f"/api/opportunities/{opportunity['id']}/stage",
        json={"stage": "ready_to_buy"},
    )

    assert response.status_code == 422


def test_opportunity_updates_return_404_for_unknown_opportunity() -> None:
    client = _test_client()

    stage_response = client.patch(
        "/api/opportunities/missing-opportunity/stage",
        json={"stage": "contact_seller"},
    )
    contact_response = client.patch(
        "/api/opportunities/missing-opportunity/contact",
        json={"seller_contact_status": "contacted"},
    )

    assert stage_response.status_code == 404
    assert stage_response.json()["detail"] == "Opportunity not found"
    assert contact_response.status_code == 404
    assert contact_response.json()["detail"] == "Opportunity not found"


def test_opportunity_decision_report_generation_persists_versioned_report() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Report generation run")
    opportunity_id = opportunity["id"]
    checklist_response = client.patch(
        f"/api/opportunities/{opportunity_id}/visit-checklist",
        json={"vin_confirmed": True, "service_records_requested": True},
    )
    assert checklist_response.status_code == 200

    first_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    second_response = client.post(f"/api/opportunities/{opportunity_id}/reports")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_report = first_response.json()
    second_report = second_response.json()
    assert first_report["version"] == 1
    assert second_report["version"] == 2
    assert first_report["opportunity_id"] == opportunity_id
    assert first_report["status"] == "partial"
    assert first_report["report_json"]["summary"]["opportunity_id"] == opportunity_id
    assert first_report["report_json"]["pricing"]["max_buy_price_cad"] is not None
    assert first_report["report_json"]["risk"]["missing_verifications"]
    assert first_report["report_json"]["visit_checklist"]["completed_count"] == 2
    assert first_report["report_json"]["visit_checklist"]["missing"]
    assert first_report["html_url"] == f"/api/opportunities/{opportunity_id}/reports/latest/html"

    latest_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == second_report["id"]
    assert latest_response.json()["version"] == 2

    report_lookup_response = client.get(f"/api/reports/{first_report['id']}")
    assert report_lookup_response.status_code == 200
    assert report_lookup_response.json()["id"] == first_report["id"]


def test_opportunity_decision_report_html_view_renders_latest_report() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Report html run")
    opportunity_id = opportunity["id"]
    client.post(f"/api/opportunities/{opportunity_id}/reports")

    response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Decision Report" in response.text
    assert "Pricing" in response.text
    assert "Visit Checklist" in response.text
    assert "Next Actions" in response.text
    assert "Missing before visit" not in response.text
    assert "missing before visit" not in response.text.lower()
    assert "Resolve missing verification data" in response.text


def test_comparable_removal_recalculates_pricing_and_versions_report() -> None:
    client = _test_client()
    run_response = client.post(
        "/api/searches/run",
        json={
            "name": "Comparable edit run",
            "natural_language_query": "2020 Honda Civic Montreal",
            "listing_limit": 25,
            "sources": "both",
            "max_candidates": 1,
        },
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]
    candidate_id = client.get(f"/api/searches/runs/{run_id}").json()["ranked_opportunities"][0]["id"]
    opportunity = client.post(f"/api/searches/runs/{run_id}/candidates/{candidate_id}/promote").json()
    opportunity_id = opportunity["id"]
    first_report = client.post(f"/api/opportunities/{opportunity_id}/reports").json()

    list_response = client.get(f"/api/opportunities/{opportunity_id}/comparables")
    assert list_response.status_code == 200
    comparable_body = list_response.json()
    assert comparable_body["included_count"] >= 2
    original_count = comparable_body["included_count"]
    original_max_buy = comparable_body["pricing_summary"]["max_buy_price_cad"]
    comparable_id = comparable_body["comparables"][0]["id"]

    update_response = client.patch(
        f"/api/comparables/{comparable_id}",
        json={"included": False, "excluded_reason": "Wrong trim and mileage band."},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["updated_comparable"]["included"] is False
    assert updated["updated_comparable"]["excluded_reason"] == "Wrong trim and mileage band."
    assert updated["included_count"] == original_count - 1
    assert updated["pricing_summary"]["comparable_count"] == original_count - 1
    assert updated["pricing_analysis"]["version"] == 1
    assert updated["pricing_summary"]["max_buy_price_cad"] is not None
    assert updated["pricing_summary"]["max_buy_price_cad"] != original_max_buy
    assert updated["report"]["version"] == first_report["version"] + 1
    assert updated["report"]["report_json"]["pricing"]["comparable_count"] == original_count - 1
    assert updated["report"]["report_json"]["comparables"]["excluded_count"] == 1

    latest_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == updated["report"]["id"]

    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    assert html_response.status_code == 200
    assert "Comparables" in html_response.text
    assert "Wrong trim and mileage band." in html_response.text


def test_comparable_removal_rejects_last_included_comparable() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Comparable final removal run")
    opportunity_id = opportunity["id"]
    comparables = client.get(f"/api/opportunities/{opportunity_id}/comparables").json()["comparables"]
    included = [comparable for comparable in comparables if comparable["included"]]
    assert included

    for comparable in included[:-1]:
        response = client.patch(
            f"/api/comparables/{comparable['id']}",
            json={"included": False, "excluded_reason": "Narrowing comparable set."},
        )
        assert response.status_code == 200

    final_response = client.patch(
        f"/api/comparables/{included[-1]['id']}",
        json={"included": False, "excluded_reason": "Remove final comparable."},
    )

    assert final_response.status_code == 400
    assert final_response.json()["detail"] == "At least one comparable must remain included"


def test_opportunity_visit_checklist_update_persists_and_marks_latest_report_stale() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Checklist stale run")
    opportunity_id = opportunity["id"]
    report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert report_response.status_code == 200
    assert report_response.json()["status"] == "partial"

    checklist_response = client.patch(
        f"/api/opportunities/{opportunity_id}/visit-checklist",
        json={
            "vin_confirmed": True,
            "service_records_requested": True,
            "lien_status_checked": True,
        },
    )

    assert checklist_response.status_code == 200
    updated = checklist_response.json()
    assert updated["visit_checklist"]["vin_confirmed"] is True
    assert updated["visit_checklist"]["service_records_requested"] is True
    assert updated["visit_checklist"]["lien_status_checked"] is True
    assert updated["visit_checklist"]["history_report_checked"] is False
    assert updated["latest_report"]["version"] == 1
    assert updated["latest_report"]["status"] == "stale"

    latest_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["status"] == "stale"
    assert latest_response.json()["report_json"]["summary"]["status"] == "stale"

    fresh_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert fresh_response.status_code == 200
    fresh_report = fresh_response.json()
    assert fresh_report["version"] == 2
    assert fresh_report["status"] == "partial"
    assert fresh_report["report_json"]["visit_checklist"]["completed_count"] == 3


def test_dealer_corrections_apply_to_future_reports_and_mark_latest_stale() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Dealer corrected VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity = response.json()["opportunity"]
    opportunity_id = opportunity["id"]
    assert "vehicle_history" in opportunity["missing_key_data"]
    assert "lien_verification" in opportunity["missing_key_data"]

    first_report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert first_report_response.status_code == 200
    assert first_report_response.json()["version"] == 1

    correction_payloads = [
        {
            "entity_type": "vehicle",
            "field_name": "trim",
            "new_value": "Touring",
            "reason": "Seller provided build sheet.",
        },
        {
            "entity_type": "vehicle",
            "field_name": "mileage_km",
            "new_value": 43210,
            "reason": "Odometer photo received.",
        },
        {
            "entity_type": "history",
            "field_name": "accident_history_status",
            "new_value": "none_reported",
            "reason": "Dealer reviewed seller history report.",
        },
        {
            "entity_type": "title",
            "field_name": "lien_status",
            "new_value": "clear",
            "reason": "PPSA search reviewed.",
        },
    ]
    latest_body = None
    for payload in correction_payloads:
        correction_response = client.post(
            f"/api/opportunities/{opportunity_id}/corrections",
            json=payload,
        )
        assert correction_response.status_code == 200
        latest_body = correction_response.json()
        assert latest_body["correction"]["new_value"] == payload["new_value"]

    assert latest_body is not None
    updated = latest_body["opportunity"]
    assert updated["latest_report"]["status"] == "stale"
    assert updated["dealer_corrections"]["active_count"] == 4
    assert updated["visit_checklist"]["history_report_checked"] is True
    assert updated["visit_checklist"]["lien_status_checked"] is True
    assert "vehicle_history" not in updated["missing_key_data"]
    assert "lien_verification" not in updated["missing_key_data"]

    list_response = client.get(f"/api/opportunities/{opportunity_id}/corrections")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 4

    fresh_report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert fresh_report_response.status_code == 200
    fresh_report = fresh_report_response.json()
    assert fresh_report["version"] == 2
    report_json = fresh_report["report_json"]
    assert report_json["vehicle"]["trim"] == "Touring"
    assert report_json["vehicle"]["mileage_km"] == 43210
    assert report_json["verification"]["history"]["status"] == "dealer_corrected"
    assert report_json["verification"]["history"]["accident_history_status"] == "none_reported"
    assert report_json["verification"]["lien_title"]["status"] == "verified"
    assert report_json["verification"]["lien_title"]["title_clearance_status"] == "clear"
    assert "vehicle_history" not in report_json["risk"]["missing_verifications"]
    assert "lien_verification" not in report_json["risk"]["missing_verifications"]
    assert len(report_json["evidence"]["dealer_corrections"]) == 4

    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    assert html_response.status_code == 200
    assert "Dealer Corrections" in html_response.text
    assert "Touring" in html_response.text


def test_dealer_corrections_validate_fields_and_unknown_opportunity() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Invalid correction run")

    invalid_response = client.post(
        f"/api/opportunities/{opportunity['id']}/corrections",
        json={"entity_type": "vehicle", "field_name": "paint_color", "new_value": "Blue"},
    )
    missing_response = client.post(
        "/api/opportunities/missing-opportunity/corrections",
        json={"entity_type": "vehicle", "field_name": "trim", "new_value": "EX"},
    )
    missing_list_response = client.get("/api/opportunities/missing-opportunity/corrections")

    assert invalid_response.status_code == 400
    assert "Unsupported correction field" in invalid_response.json()["detail"]
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Opportunity not found"
    assert missing_list_response.status_code == 404
    assert missing_list_response.json()["detail"] == "Opportunity not found"


def test_opportunity_contact_update_marks_latest_report_stale() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Contact stale run")
    opportunity_id = opportunity["id"]
    client.post(f"/api/opportunities/{opportunity_id}/reports")

    contact_response = client.patch(
        f"/api/opportunities/{opportunity_id}/contact",
        json={"seller_contact_status": "awaiting_reply"},
    )

    assert contact_response.status_code == 200
    assert contact_response.json()["latest_report"]["status"] == "stale"


def test_opportunity_stage_update_marks_latest_report_stale() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Stage stale run")
    opportunity_id = opportunity["id"]
    client.post(f"/api/opportunities/{opportunity_id}/reports")

    stage_response = client.patch(
        f"/api/opportunities/{opportunity_id}/stage",
        json={"stage": "contact_seller"},
    )

    assert stage_response.status_code == 200
    assert stage_response.json()["latest_report"]["status"] == "stale"


def test_opportunity_visit_checklist_returns_404_for_unknown_opportunity() -> None:
    client = _test_client()

    response = client.patch(
        "/api/opportunities/missing-opportunity/visit-checklist",
        json={"vin_confirmed": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Opportunity not found"


def test_opportunity_history_ingestion_updates_state_and_report() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "History intake VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity = response.json()["opportunity"]
    opportunity_id = opportunity["id"]
    assert "vehicle_history" in opportunity["missing_key_data"]
    first_report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert first_report_response.status_code == 200

    history_response = client.put(
        f"/api/opportunities/{opportunity_id}/history",
        json={
            "source_type": "carfax",
            "source_name": "CARFAX Canada",
            "report_identifier": "CFX-123",
            "title_brand": "clean",
            "accident_claims": [
                {
                    "date": "2022-04-12",
                    "amount_cad": 1400,
                    "description": "Rear bumper claim",
                    "severity": "minor",
                }
            ],
            "registration_events": [
                {"date": "2020-05-10", "province": "QC", "event": "registered"}
            ],
            "owners_count": 2,
            "odometer_records": [
                {"date": "2024-11-01", "mileage_km": 78200, "source": "service"}
            ],
            "odometer_issue": False,
            "service_records_count": 8,
            "service_records": [
                {
                    "date": "2024-11-01",
                    "mileage_km": 78200,
                    "description": "Oil service",
                }
            ],
            "import_history": [],
            "salvage_status": "clear",
            "flood_status": "clear",
            "fire_status": "clear",
            "theft_status": "clear",
            "summary": "Minor claim only; regular service records present.",
            "raw_payload": {"vendor": "carfax"},
        },
    )

    assert history_response.status_code == 200
    history_body = history_response.json()
    assert history_body["history"]["source_type"] == "carfax"
    assert history_body["history"]["accident_claims"][0]["amount_cad"] == 1400
    updated_opportunity = history_body["opportunity"]
    assert "vehicle_history" not in updated_opportunity["missing_key_data"]
    assert "lien_verification" in updated_opportunity["missing_key_data"]
    assert updated_opportunity["visit_checklist"]["history_report_checked"] is True
    assert updated_opportunity["latest_report"]["status"] == "stale"

    list_response = client.get(f"/api/opportunities/{opportunity_id}/history")
    assert list_response.status_code == 200
    assert list_response.json()["latest"]["report_identifier"] == "CFX-123"
    assert len(list_response.json()["history"]) == 1

    fresh_report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert fresh_report_response.status_code == 200
    fresh_report = fresh_report_response.json()
    assert fresh_report["status"] == "partial"
    assert fresh_report["version"] == 2
    report_json = fresh_report["report_json"]
    assert report_json["verification"]["history"]["status"] == "provided"
    assert report_json["verification"]["history"]["source"] == "CARFAX Canada"
    assert report_json["verification"]["lien_title"]["status"] == "not_verified"
    assert "vehicle_history" not in report_json["risk"]["missing_verifications"]
    assert "lien_verification" in report_json["risk"]["missing_verifications"]
    assert report_json["history_profile"]["status"] == "provided"
    assert report_json["history_profile"]["accident_claim_count"] == 1
    assert report_json["history_profile"]["accident_claim_total_cad"] == 1400
    assert report_json["history_profile"]["owners_count"] == 2
    assert "1 accident claim(s) reported" in report_json["risk"]["risk_factors"]

    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    assert html_response.status_code == 200
    assert "History Profile" in html_response.text
    assert "CARFAX Canada" in html_response.text


def test_opportunity_history_routes_return_404_for_unknown_opportunity() -> None:
    client = _test_client()

    put_response = client.put(
        "/api/opportunities/missing-opportunity/history",
        json={"source_type": "manual"},
    )
    get_response = client.get("/api/opportunities/missing-opportunity/history")

    assert put_response.status_code == 404
    assert put_response.json()["detail"] == "Opportunity not found"
    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Opportunity not found"


def test_opportunity_history_rejects_invalid_source_type() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Invalid history source run")

    response = client.put(
        f"/api/opportunities/{opportunity['id']}/history",
        json={"source_type": "unknown_vendor"},
    )

    assert response.status_code == 422


def test_opportunity_title_evidence_manual_clear_updates_state_and_report() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Manual title clear VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity = response.json()["opportunity"]
    opportunity_id = opportunity["id"]
    assert "lien_verification" in opportunity["missing_key_data"]
    client.post(f"/api/opportunities/{opportunity_id}/reports")

    title_response = client.post(
        f"/api/opportunities/{opportunity_id}/title-evidence",
        json={
            "source_type": "ppsa_lookup",
            "title_clearance_status": "clear",
            "provider": "Manual PPSA portal",
            "lookup_reference": "PPSA-123",
            "checked_at": "2026-06-14",
            "seller_name": "Jane Seller",
            "registered_owner_name": "Jane Seller",
            "ownership_verified": True,
            "payout_required": False,
            "payout_status": "not_required",
            "notes": "No active security interest found.",
        },
    )

    assert title_response.status_code == 200
    body = title_response.json()
    evidence = body["title_evidence"]
    updated = body["opportunity"]
    assert evidence["source_type"] == "ppsa_lookup"
    assert evidence["title_clearance_status"] == "clear"
    assert evidence["lookup_reference"] == "PPSA-123"
    assert updated["visit_checklist"]["lien_status_checked"] is True
    assert updated["visit_checklist"]["vin_confirmed"] is True
    assert "lien_verification" not in updated["missing_key_data"]
    assert updated["latest_report"]["status"] == "stale"
    assert updated["title_evidence"]["latest"]["title_clearance_status"] == "clear"

    list_response = client.get(f"/api/opportunities/{opportunity_id}/title-evidence")
    assert list_response.status_code == 200
    assert list_response.json()["status"] == "clear"
    assert list_response.json()["count"] == 1

    fresh_report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert fresh_report_response.status_code == 200
    report_json = fresh_report_response.json()["report_json"]
    assert report_json["verification"]["lien_title"]["status"] == "verified"
    assert report_json["verification"]["lien_title"]["lookup_reference"] == "PPSA-123"
    assert report_json["title_evidence"]["latest"]["ownership_verified"] is True
    assert "lien_verification" not in report_json["risk"]["missing_verifications"]

    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    assert html_response.status_code == 200
    assert "Title and Lien Evidence" in html_response.text
    assert "PPSA-123" in html_response.text


def test_opportunity_title_evidence_lien_found_tracks_payout_and_keeps_blocker() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Payout pending VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    opportunity_id = response.json()["opportunity"]["id"]

    title_response = client.post(
        f"/api/opportunities/{opportunity_id}/title-evidence",
        json={
            "source_type": "lender_payout",
            "title_clearance_status": "payout_pending",
            "provider": "Seller lender",
            "lienholder_name": "Example Credit Union",
            "lien_amount_cad": 7200,
            "payout_required": True,
            "payout_amount_cad": 7050,
            "payout_due_date": "2026-06-21",
            "payout_status": "requested",
            "ownership_verified": False,
            "notes": "Seller must provide payout letter before offer.",
        },
    )

    assert title_response.status_code == 200
    updated = title_response.json()["opportunity"]
    assert updated["visit_checklist"]["lien_status_checked"] is False
    assert "lien_verification" in updated["missing_key_data"]
    assert updated["title_evidence"]["latest"]["lienholder_name"] == "Example Credit Union"
    assert updated["title_evidence"]["latest"]["payout_amount_cad"] == 7050
    assert updated["title_evidence"]["latest"]["payout_status"] == "requested"

    report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert report_response.status_code == 200
    report_json = report_response.json()["report_json"]
    assert report_json["verification"]["lien_title"]["status"] == "payout_pending"
    assert "lender payout required before purchase" in report_json["risk"]["risk_factors"]
    assert "seller ownership not verified" in report_json["risk"]["risk_factors"]
    assert "lien_verification" in report_json["risk"]["missing_verifications"]


def test_opportunity_recall_compliance_clear_updates_state_and_report() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Recall clear VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity_id = response.json()["opportunity"]["id"]
    client.post(f"/api/opportunities/{opportunity_id}/reports")

    recall_response = client.post(
        f"/api/opportunities/{opportunity_id}/recall-compliance",
        json={
            "source_type": "transport_canada",
            "recall_status": "no_open_recalls",
            "compliance_status": "compliant",
            "provider": "Transport Canada recalls database",
            "lookup_reference": "TC-LOOKUP-123",
            "checked_at": "2026-06-14",
            "remedy_status": "not_required",
            "import_country": "United States",
            "import_form": "RIV Form 1",
            "riv_case_number": "RIV-123",
            "inspection_required": False,
            "notes": "No open recall found and RIV compliance evidence reviewed.",
        },
    )

    assert recall_response.status_code == 200
    body = recall_response.json()
    evidence = body["recall_compliance"]
    updated = body["opportunity"]
    assert evidence["source_type"] == "transport_canada"
    assert evidence["recall_status"] == "no_open_recalls"
    assert evidence["compliance_status"] == "compliant"
    assert evidence["lookup_reference"] == "TC-LOOKUP-123"
    assert "recall_compliance" not in updated["missing_key_data"]
    assert updated["latest_report"]["status"] == "stale"
    assert updated["recall_compliance"]["status"] == "clear"

    list_response = client.get(f"/api/opportunities/{opportunity_id}/recall-compliance")
    assert list_response.status_code == 200
    assert list_response.json()["status"] == "clear"
    assert list_response.json()["count"] == 1

    report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert report_response.status_code == 200
    report_json = report_response.json()["report_json"]
    assert report_json["verification"]["recall"]["status"] == "verified"
    assert report_json["verification"]["recall"]["lookup_reference"] == "TC-LOOKUP-123"
    assert report_json["verification"]["recall"]["compliance_status"] == "compliant"
    assert report_json["recall_compliance"]["latest"]["riv_case_number"] == "RIV-123"
    assert "recall_compliance" not in report_json["risk"]["missing_verifications"]

    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    assert html_response.status_code == 200
    assert "Recall and Compliance" in html_response.text
    assert "TC-LOOKUP-123" in html_response.text


def test_opportunity_recall_compliance_open_recall_keeps_blocker_and_risk() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Open recall VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity_id = response.json()["opportunity"]["id"]

    recall_response = client.post(
        f"/api/opportunities/{opportunity_id}/recall-compliance",
        json={
            "source_type": "oem_portal",
            "recall_status": "open_recall",
            "compliance_status": "not_applicable",
            "provider": "Honda Canada owner portal",
            "lookup_reference": "OEM-456",
            "campaign_number": "ABC123",
            "campaign_description": "Driver airbag inflator inspection.",
            "remedy_status": "required",
            "notes": "Dealer appointment required before purchase.",
        },
    )

    assert recall_response.status_code == 200
    updated = recall_response.json()["opportunity"]
    assert "recall_compliance" in updated["missing_key_data"]
    assert updated["recall_compliance"]["status"] == "open_recall"

    report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert report_response.status_code == 200
    report_json = report_response.json()["report_json"]
    assert report_json["verification"]["recall"]["status"] == "open_recall"
    assert "open recall reported" in report_json["risk"]["risk_factors"]
    assert "recall remedy status is required" in report_json["risk"]["risk_factors"]
    assert "recall_compliance" in report_json["risk"]["missing_verifications"]


def test_recall_completion_document_upload_creates_completed_evidence(tmp_path) -> None:
    client = _test_client(object_store_root=str(tmp_path / "objects"))
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Recall receipt VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity_id = response.json()["opportunity"]["id"]

    upload_response = client.post(
        f"/api/opportunities/{opportunity_id}/documents",
        data={"document_type": "recall_completion_receipt", "notes": "Dealer completed campaign ABC123."},
        files={"file": ("recall.pdf", b"%PDF-1.4 recall", "application/pdf")},
    )

    assert upload_response.status_code == 200
    body = upload_response.json()
    assert body["document"]["document_type"] == "recall_completion_receipt"
    assert body["recall_compliance"]["source_type"] == "dealer_service"
    assert body["recall_compliance"]["recall_status"] == "completed"
    assert body["recall_compliance"]["remedy_status"] == "completed"
    assert "recall_compliance" not in body["opportunity"]["missing_key_data"]
    assert body["opportunity"]["recall_compliance"]["status"] == "clear"

    list_response = client.get(f"/api/opportunities/{opportunity_id}/recall-compliance")
    assert list_response.status_code == 200
    assert list_response.json()["status"] == "clear"


def test_opportunity_wholesale_evidence_calculates_support_and_report() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Wholesale support VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity_id = response.json()["opportunity"]["id"]
    client.post(f"/api/opportunities/{opportunity_id}/reports")

    wholesale_response = client.post(
        f"/api/opportunities/{opportunity_id}/wholesale-evidence",
        json={
            "source_type": "canadian_black_book",
            "provider": "Canadian Black Book",
            "lookup_reference": "CBB-123",
            "region": "QC",
            "wholesale_low_cad": 19500,
            "wholesale_avg_cad": 21000,
            "wholesale_high_cad": 22500,
            "trade_in_value_cad": 20500,
            "retail_value_cad": 24800,
            "condition_grade": "clean",
            "buyer_fee_cad": 500,
            "transport_estimate_cad": 300,
            "reconditioning_estimate_cad": 900,
            "notes": "CBB wholesale average reviewed.",
        },
    )

    assert wholesale_response.status_code == 200
    body = wholesale_response.json()
    evidence = body["wholesale_evidence"]
    updated = body["opportunity"]
    assert evidence["source_type"] == "canadian_black_book"
    assert evidence["wholesale_avg_cad"] == 21000
    assert updated["latest_report"]["status"] == "stale"
    assert updated["wholesale_evidence"]["status"] in {"supported", "support_below_retail_max"}
    assert updated["wholesale_evidence"]["support"]["supported_max_buy_cad"] == 19510
    assert updated["wholesale_evidence"]["support"]["suggested_opening_bid_cad"] == 18729.6

    list_response = client.get(f"/api/opportunities/{opportunity_id}/wholesale-evidence")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert list_response.json()["support"]["supported_max_buy_cad"] == 19510

    report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert report_response.status_code == 200
    report_json = report_response.json()["report_json"]
    assert report_json["pricing"]["wholesale_supported_max_buy_cad"] == 19510
    assert report_json["pricing"]["wholesale_suggested_opening_bid_cad"] == 18729.6
    assert report_json["wholesale_evidence"]["latest"]["lookup_reference"] == "CBB-123"
    assert report_json["wholesale_evidence"]["support"]["source"] == "Canadian Black Book"

    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    assert html_response.status_code == 200
    assert "Wholesale and Trade-In Evidence" in html_response.text
    assert "CBB-123" in html_response.text


def test_opportunity_wholesale_auction_evidence_adds_bid_and_condition_risk() -> None:
    client = _test_client()
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Auction support VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity_id = response.json()["opportunity"]["id"]

    wholesale_response = client.post(
        f"/api/opportunities/{opportunity_id}/wholesale-evidence",
        json={
            "source_type": "openlane",
            "provider": "OPENLANE Canada",
            "lookup_reference": "OL-456",
            "auction_sale_avg_cad": 18000,
            "bid_count": 1,
            "bidder_count": 1,
            "high_bid_cad": 17500,
            "sale_price_cad": 19000,
            "condition_grade": "rough",
        },
    )

    assert wholesale_response.status_code == 200
    updated = wholesale_response.json()["opportunity"]
    assert updated["wholesale_evidence"]["support"]["supported_max_buy_cad"] == 16920

    report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert report_response.status_code == 200
    report_json = report_response.json()["report_json"]
    assert "low auction bid activity" in report_json["risk"]["risk_factors"]
    assert "low bidder count" in report_json["risk"]["risk_factors"]
    assert "auction condition grade below average" in report_json["risk"]["risk_factors"]
    assert "auction sale price exceeds wholesale supported max buy" in report_json["risk"]["risk_factors"]


def test_wholesale_document_upload_creates_evidence(tmp_path) -> None:
    client = _test_client(object_store_root=str(tmp_path / "objects"))
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Wholesale document VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity_id = response.json()["opportunity"]["id"]

    upload_response = client.post(
        f"/api/opportunities/{opportunity_id}/documents",
        data={"document_type": "manheim_mmr", "notes": "MMR screenshot saved."},
        files={"file": ("mmr.pdf", b"%PDF-1.4 mmr", "application/pdf")},
    )

    assert upload_response.status_code == 200
    body = upload_response.json()
    assert body["document"]["document_type"] == "manheim_mmr"
    assert body["wholesale_evidence"]["source_type"] == "manheim_mmr"
    assert body["wholesale_evidence"]["provider"] == "Manheim MMR"
    assert body["opportunity"]["wholesale_evidence"]["status"] == "needs_values"

    list_response = client.get(f"/api/opportunities/{opportunity_id}/wholesale-evidence")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert list_response.json()["latest"]["source_type"] == "manheim_mmr"


def test_opportunity_document_upload_lists_downloads_and_updates_workflow(tmp_path) -> None:
    client = _test_client(object_store_root=str(tmp_path / "objects"))
    response = client.post(
        "/api/opportunities/from-vin",
        json={"name": "Document fallback VIN", "vin": "2HGFC2F59LH000001", "sources": "both"},
    )
    assert response.status_code == 200
    opportunity = response.json()["opportunity"]
    opportunity_id = opportunity["id"]
    assert "vehicle_history" in opportunity["missing_key_data"]
    assert "lien_verification" in opportunity["missing_key_data"]
    report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert report_response.status_code == 200

    carfax_response = client.post(
        f"/api/opportunities/{opportunity_id}/documents",
        data={"document_type": "carfax_pdf", "notes": "Seller supplied CARFAX PDF."},
        files={"file": ("carfax.pdf", b"%PDF-1.4 carfax", "application/pdf")},
    )
    uvip_response = client.post(
        f"/api/opportunities/{opportunity_id}/documents",
        data={"document_type": "uvip"},
        files={"file": ("uvip.pdf", b"%PDF-1.4 uvip", "application/pdf")},
    )
    release_response = client.post(
        f"/api/opportunities/{opportunity_id}/documents",
        data={"document_type": "lien_release", "notes": "Lender release supplied."},
        files={"file": ("release.pdf", b"%PDF-1.4 release", "application/pdf")},
    )

    assert carfax_response.status_code == 200
    assert uvip_response.status_code == 200
    assert release_response.status_code == 200
    carfax_body = carfax_response.json()
    assert carfax_body["document"]["document_type"] == "carfax_pdf"
    assert carfax_body["document"]["document_label"] == "CARFAX PDF"
    assert carfax_body["document"]["size_bytes"] == len(b"%PDF-1.4 carfax")
    assert carfax_body["opportunity"]["latest_report"]["status"] == "stale"
    assert carfax_body["opportunity"]["visit_checklist"]["history_report_checked"] is True
    assert "vehicle_history" not in carfax_body["opportunity"]["missing_key_data"]

    uvip_body = uvip_response.json()
    assert uvip_body["title_evidence"]["source_type"] == "uvip"
    assert uvip_body["title_evidence"]["title_clearance_status"] == "needs_review"
    assert uvip_body["opportunity"]["visit_checklist"]["lien_status_checked"] is False
    assert "lien_verification" in uvip_body["opportunity"]["missing_key_data"]
    assert uvip_body["opportunity"]["documents"]["count"] == 2

    release_body = release_response.json()
    assert release_body["title_evidence"]["source_type"] == "lien_release"
    assert release_body["title_evidence"]["title_clearance_status"] == "released"
    assert release_body["opportunity"]["visit_checklist"]["lien_status_checked"] is True
    assert "lien_verification" not in release_body["opportunity"]["missing_key_data"]
    assert release_body["opportunity"]["documents"]["count"] == 3

    list_response = client.get(f"/api/opportunities/{opportunity_id}/documents")
    assert list_response.status_code == 200
    documents = list_response.json()["documents"]
    assert [document["document_type"] for document in documents] == ["lien_release", "uvip", "carfax_pdf"]

    title_list_response = client.get(f"/api/opportunities/{opportunity_id}/title-evidence")
    assert title_list_response.status_code == 200
    assert title_list_response.json()["status"] == "released"
    assert [item["title_clearance_status"] for item in title_list_response.json()["evidence"]] == [
        "released",
        "needs_review",
    ]

    download_response = client.get(carfax_body["document"]["download_url"])
    assert download_response.status_code == 200
    assert download_response.content == b"%PDF-1.4 carfax"
    assert download_response.headers["content-type"] == "application/pdf"
    assert 'filename="carfax.pdf"' in download_response.headers["content-disposition"]

    fresh_report_response = client.post(f"/api/opportunities/{opportunity_id}/reports")
    assert fresh_report_response.status_code == 200
    report_json = fresh_report_response.json()["report_json"]
    assert report_json["verification"]["history"]["status"] == "document_uploaded"
    assert report_json["verification"]["lien_title"]["status"] == "verified"
    assert report_json["title_evidence"]["latest"]["title_clearance_status"] == "released"
    assert [document["document_type"] for document in report_json["evidence"]["uploaded_documents"]] == [
        "lien_release",
        "uvip",
        "carfax_pdf",
    ]
    assert fresh_report_response.json()["status"] == "preliminary"

    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    assert html_response.status_code == 200
    assert "Uploaded Evidence" in html_response.text
    assert "Title and Lien Evidence" in html_response.text
    assert "carfax.pdf" in html_response.text


def test_opportunity_document_upload_validation_and_404s(tmp_path) -> None:
    client = _test_client(object_store_root=str(tmp_path / "objects"))
    opportunity = _promote_first_fixture_candidate(client, name="Invalid document upload")
    opportunity_id = opportunity["id"]

    invalid_type_response = client.post(
        f"/api/opportunities/{opportunity_id}/documents",
        data={"document_type": "bank_statement"},
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    invalid_content_response = client.post(
        f"/api/opportunities/{opportunity_id}/documents",
        data={"document_type": "seller_document"},
        files={"file": ("doc.bin", b"binary", "application/octet-stream")},
    )
    missing_opportunity_response = client.post(
        "/api/opportunities/missing-opportunity/documents",
        data={"document_type": "seller_document"},
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    missing_list_response = client.get("/api/opportunities/missing-opportunity/documents")
    missing_download_response = client.get(
        f"/api/opportunities/{opportunity_id}/documents/missing-document/download"
    )

    assert invalid_type_response.status_code == 400
    assert "Unsupported document type" in invalid_type_response.json()["detail"]
    assert invalid_content_response.status_code == 400
    assert "Unsupported document content type" in invalid_content_response.json()["detail"]
    assert missing_opportunity_response.status_code == 404
    assert missing_opportunity_response.json()["detail"] == "Opportunity not found"
    assert missing_list_response.status_code == 404
    assert missing_list_response.json()["detail"] == "Opportunity not found"
    assert missing_download_response.status_code == 404
    assert missing_download_response.json()["detail"] == "Document not found"


def test_opportunity_decision_report_routes_return_404_for_missing_records() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Report missing run")
    opportunity_id = opportunity["id"]

    latest_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest")
    html_response = client.get(f"/api/opportunities/{opportunity_id}/reports/latest/html")
    missing_opportunity_response = client.post("/api/opportunities/missing-opportunity/reports")
    missing_report_response = client.get("/api/reports/missing-report")

    assert latest_response.status_code == 404
    assert latest_response.json()["detail"] == "Decision report not found"
    assert html_response.status_code == 404
    assert html_response.json()["detail"] == "Decision report not found"
    assert missing_opportunity_response.status_code == 404
    assert missing_opportunity_response.json()["detail"] == "Opportunity not found"
    assert missing_report_response.status_code == 404
    assert missing_report_response.json()["detail"] == "Decision report not found"


def test_opportunity_feedback_persists_with_latest_report_link_and_lists_newest_first() -> None:
    client = _test_client()
    opportunity = _promote_first_fixture_candidate(client, name="Feedback run")
    opportunity_id = opportunity["id"]
    report = client.post(f"/api/opportunities/{opportunity_id}/reports").json()

    first_response = client.post(
        f"/api/opportunities/{opportunity_id}/feedback",
        json={
            "usefulness_rating": 4,
            "accuracy_rating": 3,
            "dealer_decision": "pursue",
            "missing_info": ["lien status", "service records"],
            "incorrect_info": ["trim uncertainty"],
            "notes": "Good enough to call seller.",
        },
    )
    second_response = client.post(
        f"/api/opportunities/{opportunity_id}/feedback",
        json={
            "usefulness_rating": 2,
            "accuracy_rating": 2,
            "dealer_decision": "pass",
            "missing_info": ["accident history"],
            "incorrect_info": [],
        },
    )

    assert first_response.status_code == 200
    first = first_response.json()
    assert first["report_id"] == report["id"]
    assert first["report_version"] == report["version"]
    assert first["missing_info"] == ["lien status", "service records"]
    assert first["incorrect_info"] == ["trim uncertainty"]

    assert second_response.status_code == 200
    list_response = client.get(f"/api/opportunities/{opportunity_id}/feedback")
    assert list_response.status_code == 200
    feedback_items = list_response.json()["feedback"]
    assert [item["id"] for item in feedback_items] == [second_response.json()["id"], first["id"]]

    global_response = client.get("/api/feedback")
    assert global_response.status_code == 200
    assert len(global_response.json()["feedback"]) == 2


def test_pilot_feedback_summary_aggregates_ratings_decisions_and_common_issues() -> None:
    client = _test_client()
    first = _promote_first_fixture_candidate(client, name="Feedback summary one")
    second = _promote_first_fixture_candidate(client, name="Feedback summary two")

    client.post(
        f"/api/opportunities/{first['id']}/feedback",
        json={
            "usefulness_rating": 5,
            "accuracy_rating": 4,
            "dealer_decision": "pursue",
            "missing_info": ["lien status"],
            "incorrect_info": ["mileage"],
        },
    )
    client.post(
        f"/api/opportunities/{second['id']}/feedback",
        json={
            "usefulness_rating": 3,
            "accuracy_rating": 2,
            "dealer_decision": "pass",
            "missing_info": ["lien status", "service records"],
            "incorrect_info": ["trim"],
        },
    )

    response = client.get("/api/feedback/summary")

    assert response.status_code == 200
    summary = response.json()
    assert summary["total_feedback"] == 2
    assert summary["tested_opportunities"] == 2
    assert summary["average_usefulness"] == 4.0
    assert summary["average_accuracy"] == 3.0
    assert summary["decision_counts"] == {"pass": 1, "pursue": 1}
    assert summary["common_missing_info"][0] == {"value": "lien status", "count": 2}


def test_opportunity_feedback_validates_ratings_and_unknown_opportunity() -> None:
    client = _test_client()

    invalid_response = client.post(
        "/api/opportunities/missing-opportunity/feedback",
        json={"usefulness_rating": 6, "accuracy_rating": 1},
    )
    missing_response = client.post(
        "/api/opportunities/missing-opportunity/feedback",
        json={"usefulness_rating": 3, "accuracy_rating": 3},
    )
    missing_list_response = client.get("/api/opportunities/missing-opportunity/feedback")

    assert invalid_response.status_code == 422
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Opportunity not found"
    assert missing_list_response.status_code == 404
    assert missing_list_response.json()["detail"] == "Opportunity not found"


def test_opportunity_detail_returns_404_for_unknown_opportunity() -> None:
    client = _test_client()

    response = client.get("/api/opportunities/missing-opportunity")

    assert response.status_code == 404
    assert response.json()["detail"] == "Opportunity not found"


def test_saved_search_run_without_body_returns_404_for_unknown_search() -> None:
    client = _test_client()

    response = client.post("/api/searches/missing-search/run")

    assert response.status_code == 404
    assert response.json()["detail"] == "Saved search not found"


def test_ad_hoc_search_run_api_accepts_structured_filters_and_source_selection() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/run",
        json={
            "name": "AutoTrader Civic shortlist",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "year_min": 2020,
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["search_id"]
    assert body["run_id"]
    assert body["sources"] == ["autotrader"]
    assert body["source_statuses"][0]["source_name"] == "autotrader"
    assert body["source_statuses"][0]["status"] == "ok"
    assert body["source_statuses"][0]["diagnostics"]["app_mode"] == "fixture"
    assert body["source_statuses"][0]["diagnostics"]["fetch_method"] == "fixture"
    assert body["source_statuses"][0]["diagnostics"]["source_role"] == "search"
    assert body["normalized_filters"]["make"] == "Honda"
    assert body["normalized_filters"]["limit"] == 25
    assert len(body["ranked_opportunities"]) == 2
    assert {item["source"] for item in body["ranked_opportunities"]} == {"autotrader"}


def test_ad_hoc_search_run_api_accepts_natural_language_query() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/run",
        json={
            "name": "Natural language shortlist",
            "natural_language_query": "2020 Honda Civic Montreal",
            "listing_limit": 25,
            "sources": "both",
            "max_candidates": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["normalized_filters"]["query"] == "2020 Honda Civic Montreal"
    assert body["normalized_filters"]["make"] == "Honda"
    assert body["normalized_filters"]["model"] == "Civic"
    assert body["normalized_filters"]["year_min"] == 2020
    assert body["normalized_filters"]["location_city"] == "Montreal"
    assert body["interpreted_filters"]["make"] == "Honda"
    assert body["interpretation"]["confidence"] > 0
    assert body["sources"] == ["kijiji", "autotrader"]
    assert 1 <= len(body["ranked_opportunities"]) <= 3


def test_ad_hoc_search_run_api_accepts_listing_url_analysis() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/run",
        json={
            "name": "Single Kijiji listing",
            "listing_url": "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
            "vin": "2HGFC2F59LH000001",
            "sources": "both",
            "listing_limit": 25,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"]
    assert body["intake_mode"] == "single_listing"
    assert body["listing_url"] == "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001"
    assert body["vin"] == "2HGFC2F59LH000001"
    assert body["direct_promote_available"] is True
    assert len(body["ranked_opportunities"]) == 1
    target_status = body["source_statuses"][0]
    assert target_status["diagnostics"]["source_role"] == "target_listing"
    assert target_status["diagnostics"]["parser"] == "listing_detail"
    candidate = body["ranked_opportunities"][0]
    assert candidate["intake_mode"] == "single_listing"
    assert candidate["direct_promote_available"] is True
    assert candidate["source"] == "kijiji"
    assert candidate["vin"] == "2HGFC2F59LH000001"
    assert candidate["image_count"] > 0

    run_detail = client.get(f"/api/searches/runs/{body['run_id']}").json()
    assert run_detail["intake_mode"] == "single_listing"
    assert run_detail["direct_promote_available"] is True


def test_opportunity_from_listing_promotes_kijiji_listing_with_vin_context() -> None:
    client = _test_client()

    response = client.post(
        "/api/opportunities/from-listing",
        json={
            "name": "Direct Kijiji intake",
            "listing_url": "https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001",
            "vin": "2HGFC2F59LH000001",
            "sources": "both",
            "listing_limit": 25,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "promoted"
    assert body["run_id"]
    assert body["candidate_id"]
    assert body["intake_mode"] == "single_listing"
    opportunity = body["opportunity"]
    assert opportunity["candidate"]["source"] == "kijiji"
    assert opportunity["candidate"]["vin"] == "2HGFC2F59LH000001"
    assert opportunity["visit_checklist"]["vin_confirmed"] is True

    report_response = client.post(f"/api/opportunities/{opportunity['id']}/reports")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["report_json"]["evidence"]["intake_mode"] == "single_listing"
    assert report["report_json"]["evidence"]["source_url"] == opportunity["candidate"]["source_url"]


def test_opportunity_from_listing_promotes_autotrader_listing() -> None:
    client = _test_client()

    response = client.post(
        "/api/opportunities/from-listing",
        json={
            "name": "Direct AutoTrader intake",
            "listing_url": "https://www.autotrader.ca/a/honda/civic/montreal/quebec/19_001",
            "sources": "autotrader",
            "listing_limit": 25,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "promoted"
    assert body["opportunity"]["candidate"]["source"] == "autotrader"
    assert body["opportunity"]["visit_checklist"]["vin_confirmed"] is False


def test_opportunity_from_listing_rejects_unsupported_listing_domain() -> None:
    client = _test_client()

    response = client.post(
        "/api/opportunities/from-listing",
        json={"listing_url": "https://example.com/listing/123"},
    )

    assert response.status_code == 400
    assert "Unsupported listing URL source" in response.json()["detail"]


def test_ad_hoc_search_run_api_accepts_vin_only_analysis() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/run",
        json={
            "name": "VIN only",
            "vin": "2HGFC2F59LH000001",
            "sources": "both",
            "listing_limit": 25,
            "structured_filters": {
                "model": "Civic",
                "location_city": "Montreal",
                "location_province": "QC",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"]
    assert body["intake_mode"] == "vin"
    assert body["vin"] == "2HGFC2F59LH000001"
    assert body["direct_promote_available"] is True
    assert body["ranked_opportunities"]
    candidate = body["ranked_opportunities"][0]
    assert candidate["vin"] == "2HGFC2F59LH000001"
    assert candidate["source"] == "vin"
    assert candidate["missing_data"] == ["vehicle_history", "lien_verification"]
    statuses = {status["source_name"]: status for status in body["source_statuses"]}
    assert statuses["vin_decode"]["status"] == "ok"
    assert statuses["vehicle_history"]["status"] == "blocked"
    assert statuses["lien_title"]["status"] == "blocked"
    assert statuses["recall"]["status"] == "blocked"


def test_saved_vin_search_runs_and_updates_last_run() -> None:
    client = _test_client()

    create_response = client.post(
        "/api/searches",
        json={
            "name": "VIN saved search",
            "vin": "2HGFC2F59LH000001",
            "sources": "both",
            "structured_filters": {"model": "Civic"},
        },
    )
    assert create_response.status_code == 200
    search_id = create_response.json()["id"]
    assert create_response.json()["mode"] == "vin"

    run_response = client.post(f"/api/searches/{search_id}/run")

    assert run_response.status_code == 200
    assert run_response.json()["intake_mode"] == "vin"
    detail_response = client.get(f"/api/searches/{search_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["last_run_at"] is not None


def test_opportunity_from_vin_promotes_and_generates_partial_report() -> None:
    client = _test_client()

    response = client.post(
        "/api/opportunities/from-vin",
        json={
            "name": "Direct VIN intake",
            "vin": "2HGFC2F59LH000001",
            "sources": "both",
            "model": "Civic",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "promoted"
    assert body["intake_mode"] == "vin"
    opportunity = body["opportunity"]
    assert opportunity["candidate"]["source"] == "vin"
    assert opportunity["candidate"]["vin"] == "2HGFC2F59LH000001"
    assert opportunity["visit_checklist"]["vin_confirmed"] is True

    report_response = client.post(f"/api/opportunities/{opportunity['id']}/reports")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["status"] == "partial"
    assert report["report_json"]["evidence"]["intake_mode"] == "vin"
    assert report["report_json"]["verification"]["vin"]["status"] == "verified_format"
    assert report["report_json"]["verification"]["history"]["status"] == "not_verified"
    assert report["report_json"]["verification"]["lien_title"]["status"] == "not_verified"
    assert report["report_json"]["verification"]["recall"]["status"] == "not_checked"


def test_vin_only_analysis_rejects_invalid_vin() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/run",
        json={"name": "Invalid VIN", "vin": "INVALIDVIN123"},
    )
    promote_response = client.post(
        "/api/opportunities/from-vin",
        json={"vin": "INVALIDVIN123"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "VIN must be 17 characters"
    assert promote_response.status_code == 400
    assert promote_response.json()["detail"] == "VIN must be 17 characters"


def test_ad_hoc_search_run_api_rejects_unsupported_listing_domain() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/run",
        json={
            "name": "Unsupported listing",
            "listing_url": "https://example.com/listing/123",
        },
    )

    assert response.status_code == 400
    assert "Unsupported listing URL source" in response.json()["detail"]


def _test_client(object_store_root: str | None = None) -> TestClient:
    engine = _memory_engine()
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session() -> Generator[Session]:
        with testing_session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: Settings(
        SCRAPING_FIXTURE_MODE=True,
        OBJECT_STORE_ROOT=object_store_root or "var/test-object-store",
    )
    client = TestClient(app)
    client.testing_session = testing_session
    return client


def _promote_first_fixture_candidate(client: TestClient, name: str) -> dict:
    run_response = client.post(
        "/api/searches/run",
        json={
            "name": name,
            "natural_language_query": "2020 Honda Civic Montreal",
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 1,
        },
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]
    candidate_id = client.get(f"/api/searches/runs/{run_id}").json()["ranked_opportunities"][0]["id"]
    promote_response = client.post(f"/api/searches/runs/{run_id}/candidates/{candidate_id}/promote")
    assert promote_response.status_code == 200
    return promote_response.json()


def _memory_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
