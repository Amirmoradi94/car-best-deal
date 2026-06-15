from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import create_app
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session


def test_dashboard_static_entrypoint_serves_app_shell() -> None:
    client = _test_client()

    response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "Opportunity Finder" in response.text
    assert "Dealer settings" in response.text
    assert "Analyze + Promote" in response.text
    assert "Interpret" in response.text
    assert "Scheduled refresh" in response.text
    assert "Alerts" in response.text
    assert 'id="alerts"' in response.text
    assert 'id="opportunities"' in response.text
    assert 'id="pilot-feedback-summary"' in response.text
    assert "/dashboard/app.js" in response.text
    assert "/dashboard/styles.css" in response.text


def test_dashboard_static_assets_are_available() -> None:
    client = _test_client()

    script_response = client.get("/dashboard/app.js")
    style_response = client.get("/dashboard/styles.css")

    assert script_response.status_code == 200
    assert "buildPayload" in script_response.text
    assert "schedule_cron" in script_response.text
    assert "previewInterpretation" in script_response.text
    assert "renderInterpretation" in script_response.text
    assert "loadAlerts" in script_response.text
    assert "markAlertRead" in script_response.text
    assert "alertPriceLabel" in script_response.text
    assert "loadSettings" in script_response.text
    assert "saveSettings" in script_response.text
    assert "promoteCandidate" in script_response.text
    assert "analyzeAndPromoteListing" in script_response.text
    assert "diagnosticPills" in script_response.text
    assert "submitOpportunityFeedback" in script_response.text
    assert "renderPilotFeedbackSummary" in script_response.text
    assert "downloadLatestOpportunityReport" in script_response.text
    assert "data-download-opportunity-report-pdf" in script_response.text
    assert "data-download-opportunity-report-csv" in script_response.text
    assert "uploadOpportunityDocument" in script_response.text
    assert "documentTypeOptions" in script_response.text
    assert "submitTitleEvidence" in script_response.text
    assert "titleEvidenceFormHtml" in script_response.text
    assert "submitRecallCompliance" in script_response.text
    assert "transport_canada_recall_report" in script_response.text
    assert "submitWholesaleEvidence" in script_response.text
    assert "cbb_valuation" in script_response.text
    assert "openlane_auction_report" in script_response.text
    assert "submitDealerCorrection" in script_response.text
    assert "dealerCorrectionFormHtml" in script_response.text
    assert "accidentCorrectionOptions" in script_response.text
    assert "lienCorrectionOptions" in script_response.text
    assert "loadOpportunityComparables" in script_response.text
    assert "removeComparable" in script_response.text
    assert "comparableEditorHtml" in script_response.text
    assert "priceHistoryHtml" in script_response.text
    assert style_response.status_code == 200
    assert ".opportunity-card" in style_response.text
    assert ".settings-panel" in style_response.text
    assert ".alert-card" in style_response.text
    assert ".interpretation-card" in style_response.text
    assert ".feedback-grid" in style_response.text
    assert ".document-upload-group" in style_response.text
    assert ".title-evidence-group" in style_response.text
    assert ".recall-compliance-group" in style_response.text
    assert ".wholesale-evidence-group" in style_response.text
    assert ".dealer-corrections-group" in style_response.text
    assert ".dealer-correction-grid" in style_response.text
    assert ".comparable-editing-group" in style_response.text
    assert ".comparable-row" in style_response.text


def test_dashboard_search_api_contract_includes_rendered_fields() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/run",
        json={
            "name": "Dashboard fixture run",
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

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"]
    assert body["intake_mode"] == "discovery"
    assert body["direct_promote_available"] is False
    assert body["ranked_opportunities"]

    run_response = client.get(f"/api/searches/runs/{body['run_id']}")
    assert run_response.status_code == 200
    run_body = run_response.json()
    candidate = run_body["ranked_opportunities"][0]

    for field in [
        "id",
        "title",
        "source",
        "source_url",
        "asking_price_cad",
        "deal_score",
        "recommendation",
        "estimated_retail_value_cad",
        "max_buy_price_cad",
        "is_overpriced",
        "missing_data",
        "image_count",
        "image_risk_reasons",
        "confidence_by_section",
        "selected",
        "hidden",
        "seller_contact_status",
        "seller_notes",
        "opportunity_id",
        "intake_mode",
        "direct_promote_available",
    ]:
        assert field in candidate

    assert "price_history" in candidate["pricing_summary"]
    assert candidate["pricing_summary"]["price_history"]["latest_listing_snapshot_id"]
    assert run_body["source_statuses"]
    assert all("source_name" in status for status in run_body["source_statuses"])
    assert all("diagnostics" in status for status in run_body["source_statuses"])


def test_search_interpret_endpoint_returns_applied_filters() -> None:
    client = _test_client()

    response = client.post(
        "/api/searches/interpret",
        json={
            "natural_language_query": "2020 Honda Civic under $20k Montreal private seller",
            "structured_filters": {
                "location_city": "Laval",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["interpreted_filters"]["make"] == "Honda"
    assert body["interpreted_filters"]["model"] == "Civic"
    assert body["interpreted_filters"]["year_min"] == 2020
    assert body["interpreted_filters"]["price_max_cad"] == 20000
    assert body["interpreted_filters"]["seller_type"] == "private"
    assert body["applied_filters"]["location_city"] == "Laval"
    assert body["applied_filters"]["make"] == "Honda"
    assert body["interpretation"]["confidence"] > 0


def test_settings_api_persists_dealer_scoring_settings() -> None:
    client = _test_client()

    default_response = client.get("/api/settings")

    assert default_response.status_code == 200
    assert default_response.json()["target_profit_cad"] == 2500

    update_response = client.patch(
        "/api/settings",
        json={
            "target_profit_cad": 3200,
            "risk_tolerance": "low",
            "preferred_brands": ["Honda", "Honda", "Toyota"],
            "preferred_models": ["Civic", "Accord"],
            "default_search_radius_km": 75,
            "include_overpriced_default": True,
            "candidate_score_threshold": 68,
            "max_candidate_count": 3,
            "max_images_per_candidate": 4,
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["target_profit_cad"] == 3200
    assert body["risk_tolerance"] == "low"
    assert body["preferred_brands"] == ["Honda", "Toyota"]
    assert body["preferred_models"] == ["Civic", "Accord"]
    assert body["default_search_radius_km"] == 75
    assert body["include_overpriced_default"] is True
    assert body["candidate_score_threshold"] == 68
    assert body["max_candidate_count"] == 3
    assert body["max_images_per_candidate"] == 4

    persisted_response = client.get("/api/settings")

    assert persisted_response.status_code == 200
    assert persisted_response.json()["target_profit_cad"] == 3200


def test_search_run_uses_persisted_dealer_settings_for_scoring_and_caps() -> None:
    client = _test_client()

    settings_response = client.patch(
        "/api/settings",
        json={
            "target_profit_cad": 4100,
            "risk_tolerance": "high",
            "preferred_brands": ["Honda"],
            "preferred_models": ["Civic"],
            "max_candidate_count": 1,
            "max_images_per_candidate": 2,
        },
    )
    assert settings_response.status_code == 200

    run_response = client.post(
        "/api/searches/run",
        json={
            "name": "Settings-backed run",
            "structured_filters": {
                "make": "Honda",
                "model": "Civic",
                "year_min": 2020,
                "location_city": "Montreal",
                "location_province": "QC",
            },
            "listing_limit": 25,
            "sources": "autotrader",
            "max_candidates": 5,
        },
    )

    assert run_response.status_code == 200
    body = run_response.json()
    assert len(body["ranked_opportunities"]) == 1
    run_detail = client.get(f"/api/searches/runs/{body['run_id']}").json()
    persisted_candidate = run_detail["ranked_opportunities"][0]
    assert persisted_candidate["pricing_summary"]["target_profit_cad"] == 4100


def test_source_health_endpoint_reports_fixture_policy() -> None:
    client = _test_client()

    response = client.get("/api/settings/source-health")

    assert response.status_code == 200
    body = response.json()
    assert body["app_mode"] == "fixture"
    assert body["policy"] == "fixture_only"
    assert body["broad_live_discovery_enabled"] is False
    assert body["sources"]


def _test_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session() -> Generator[Session]:
        with testing_session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: Settings(SCRAPING_FIXTURE_MODE=True)
    return TestClient(app)
