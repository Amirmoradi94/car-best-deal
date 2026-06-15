from types import SimpleNamespace

from app.cli import pilot_smoke


def test_pilot_smoke_requires_live_url_intake_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        pilot_smoke,
        "_request_json",
        lambda method, url, payload=None: {
            "app_mode": "fixture",
            "fixture_mode": True,
            "live_url_intake_enabled": False,
        },
    )

    exit_code, artifact = pilot_smoke.run(
        _args(
            tmp_path,
            urls=["https://www.kijiji.ca/v-cars-trucks/montreal/2020-honda-civic-ex/001"],
            allow_fixture=False,
        )
    )

    assert exit_code == 2
    assert artifact["ready_for_real_test"] is False
    assert "Live URL intake is not enabled" in artifact["error"]
    assert (tmp_path / "pilot-smoke.json").exists()


def test_pilot_smoke_runs_listing_report_and_feedback_flow(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/api/settings/source-health"):
            return {
                "app_mode": "pilot",
                "fixture_mode": False,
                "live_url_intake_enabled": True,
            }
        if url.endswith("/api/opportunities/from-listing"):
            return {
                "run_id": "run-001",
                "candidate_id": "candidate-001",
                "source_statuses": [
                    {
                        "source_name": "kijiji",
                        "status": "ok",
                        "diagnostics": {"fetch_method": "zyte", "source_role": "target_listing"},
                    }
                ],
                "opportunity": {
                    "id": "opportunity-001",
                    "candidate": {
                        "title": "2020 Honda Civic EX",
                        "source": "kijiji",
                        "source_url": "https://www.kijiji.ca/example",
                        "vin": "2HGFC2F59LH000001",
                        "asking_price_cad": 18200,
                        "deal_score": 87,
                        "recommendation": "buy",
                        "image_count": 8,
                        "missing_data": [],
                        "image_risk_reasons": [],
                    },
                },
            }
        if url.endswith("/api/opportunities/opportunity-001/reports"):
            return {
                "id": "report-001",
                "version": 1,
                "status": "fresh",
                "recommendation": "buy",
                "html_url": "/api/opportunities/opportunity-001/reports/latest/html",
                "report_json": {"next_actions": ["Call seller"]},
            }
        if url.endswith("/api/opportunities/opportunity-001/feedback"):
            return {"id": "feedback-001"}
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(pilot_smoke, "_request_json", fake_request)

    exit_code, artifact = pilot_smoke.run(
        _args(
            tmp_path,
            urls=["https://www.kijiji.ca/example"],
            vin="2HGFC2F59LH000001",
            submit_smoke_feedback=True,
        )
    )

    assert exit_code == 0
    assert artifact["ready_for_real_test"] is True
    result = artifact["results"][0]
    assert result["status"] == "ok"
    assert result["opportunity_id"] == "opportunity-001"
    assert result["report_id"] == "report-001"
    assert result["feedback_id"] == "feedback-001"
    assert result["source_statuses"][0]["diagnostics"]["fetch_method"] == "zyte"
    assert calls[1][2]["vin"] == "2HGFC2F59LH000001"


def test_pilot_smoke_captures_api_error_per_listing(tmp_path, monkeypatch) -> None:
    def fake_request(method, url, payload=None):
        if url.endswith("/api/settings/source-health"):
            return {
                "app_mode": "pilot",
                "fixture_mode": False,
                "live_url_intake_enabled": True,
            }
        raise pilot_smoke.ApiRequestError(400, {"detail": "Unsupported listing URL source"})

    monkeypatch.setattr(pilot_smoke, "_request_json", fake_request)

    exit_code, artifact = pilot_smoke.run(_args(tmp_path, urls=["https://example.com/listing/123"]))

    assert exit_code == 1
    result = artifact["results"][0]
    assert result["status"] == "failed"
    assert result["error"] == {
        "type": "api",
        "status_code": 400,
        "body": {"detail": "Unsupported listing URL source"},
    }


def _args(tmp_path, **overrides):
    defaults = {
        "urls": [],
        "url_file": None,
        "base_url": "http://127.0.0.1:8000",
        "sources": "both",
        "listing_limit": 25,
        "location_city": "Montreal",
        "location_province": "QC",
        "radius_km": 50,
        "name_prefix": "Pilot smoke",
        "vin": None,
        "submit_smoke_feedback": False,
        "allow_fixture": False,
        "output": str(tmp_path / "pilot-smoke.json"),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)
