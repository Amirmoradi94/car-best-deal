from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT_PATH = "var/pilot-smoke/latest.json"


@dataclass(frozen=True)
class ListingCase:
    url: str
    vin: str | None = None


class ApiRequestError(RuntimeError):
    def __init__(self, status_code: int, body: dict | str | None) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"API request failed with HTTP {status_code}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a real-test smoke pass for pasted marketplace listing URLs."
    )
    parser.add_argument("urls", nargs="*", help="Kijiji or AutoTrader listing URLs to test.")
    parser.add_argument("--url-file", help="Text file with one URL per line, or URL|VIN per line.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Running API base URL.")
    parser.add_argument("--sources", choices=["both", "kijiji", "autotrader"], default="both")
    parser.add_argument("--listing-limit", type=int, default=25)
    parser.add_argument("--location-city", default="Montreal")
    parser.add_argument("--location-province", default="QC")
    parser.add_argument("--radius-km", type=int, default=50)
    parser.add_argument("--name-prefix", default="Pilot smoke")
    parser.add_argument("--vin", help="VIN to attach when exactly one URL is supplied.")
    parser.add_argument(
        "--submit-smoke-feedback",
        action="store_true",
        help="Submit neutral placeholder feedback after report generation.",
    )
    parser.add_argument(
        "--allow-fixture",
        action="store_true",
        help="Allow fixture-mode smoke runs. By default, live URL intake is required.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Write JSON artifact to this path.")
    return parser


def run(args: argparse.Namespace) -> tuple[int, dict]:
    started_at = _now()
    cases = _load_cases(args.urls, args.url_file, args.vin)
    artifact: dict = {
        "started_at": started_at,
        "finished_at": None,
        "base_url": args.base_url.rstrip("/"),
        "allow_fixture": bool(args.allow_fixture),
        "case_count": len(cases),
        "source_health": None,
        "results": [],
        "ready_for_real_test": False,
    }

    if not cases:
        artifact["error"] = "Provide at least one URL or --url-file."
        return _finish(2, artifact, args.output)

    try:
        source_health = _request_json("GET", _join_url(args.base_url, "/api/settings/source-health"))
    except Exception as exc:
        artifact["error"] = f"Could not read source health: {exc}"
        return _finish(2, artifact, args.output)

    artifact["source_health"] = source_health
    live_url_intake = bool(source_health.get("live_url_intake_enabled"))
    fixture_mode = bool(source_health.get("fixture_mode"))
    if not live_url_intake and not args.allow_fixture:
        artifact["error"] = (
            "Live URL intake is not enabled. Set APP_MODE=pilot, "
            "SCRAPING_FIXTURE_MODE=false, SCRAPING_USE_ZYTE=true, and ZYTE_API_KEY, "
            "or rerun with --allow-fixture for a local fixture smoke."
        )
        return _finish(2, artifact, args.output)
    if fixture_mode and not args.allow_fixture:
        artifact["error"] = "API is in fixture mode. Rerun with --allow-fixture or switch to pilot live URL mode."
        return _finish(2, artifact, args.output)

    for index, case in enumerate(cases, start=1):
        artifact["results"].append(_run_case(args, case, index))

    failures = [item for item in artifact["results"] if item["status"] != "ok"]
    artifact["ready_for_real_test"] = not failures and (live_url_intake or args.allow_fixture)
    return _finish(1 if failures else 0, artifact, args.output)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code, artifact = run(args)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return exit_code


def _run_case(args: argparse.Namespace, case: ListingCase, index: int) -> dict:
    result: dict = {
        "index": index,
        "listing_url": case.url,
        "vin": case.vin,
        "status": "pending",
        "opportunity_id": None,
        "candidate_id": None,
        "run_id": None,
        "report_id": None,
        "feedback_id": None,
        "source_statuses": [],
        "candidate": None,
        "report": None,
        "error": None,
    }
    try:
        intake = _request_json(
            "POST",
            _join_url(args.base_url, "/api/opportunities/from-listing"),
            {
                "name": f"{args.name_prefix} {index}",
                "listing_url": case.url,
                "vin": case.vin,
                "sources": args.sources,
                "listing_limit": args.listing_limit,
                "location_city": args.location_city,
                "location_province": args.location_province,
                "radius_km": args.radius_km,
            },
        )
        opportunity = intake.get("opportunity") or {}
        candidate = opportunity.get("candidate") or {}
        opportunity_id = opportunity.get("id")
        result.update(
            {
                "status": "intake_ok",
                "opportunity_id": opportunity_id,
                "candidate_id": intake.get("candidate_id"),
                "run_id": intake.get("run_id"),
                "source_statuses": intake.get("source_statuses") or [],
                "candidate": _candidate_summary(candidate, opportunity),
            }
        )
        if not opportunity_id:
            raise RuntimeError("Intake response did not include an opportunity ID.")

        report = _request_json("POST", _join_url(args.base_url, f"/api/opportunities/{opportunity_id}/reports"))
        result["report_id"] = report.get("id")
        result["report"] = _report_summary(report)

        if args.submit_smoke_feedback:
            feedback = _request_json(
                "POST",
                _join_url(args.base_url, f"/api/opportunities/{opportunity_id}/feedback"),
                {
                    "usefulness_rating": 3,
                    "accuracy_rating": 3,
                    "dealer_decision": "undecided",
                    "missing_info": ["smoke test placeholder"],
                    "incorrect_info": [],
                    "notes": "Automated pilot smoke feedback placeholder.",
                },
            )
            result["feedback_id"] = feedback.get("id")

        result["status"] = "ok"
    except ApiRequestError as exc:
        result["status"] = "failed"
        result["error"] = {"type": "api", "status_code": exc.status_code, "body": exc.body}
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = {"type": "runtime", "message": str(exc)}
    return result


def _request_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8")
        try:
            body: dict | str | None = json.loads(body_text) if body_text else None
        except json.JSONDecodeError:
            body = body_text
        raise ApiRequestError(exc.code, body) from exc


def _load_cases(urls: list[str], url_file: str | None, vin: str | None) -> list[ListingCase]:
    raw_cases: list[ListingCase] = []
    for url in urls:
        raw_cases.append(ListingCase(url=url.strip(), vin=None))
    if url_file:
        for line in Path(url_file).read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "|" in stripped:
                url, line_vin = [part.strip() for part in stripped.split("|", 1)]
                raw_cases.append(ListingCase(url=url, vin=line_vin or None))
            else:
                raw_cases.append(ListingCase(url=stripped, vin=None))
    if vin:
        if len(raw_cases) != 1:
            raise SystemExit("--vin can only be used when exactly one URL is supplied.")
        raw_cases = [ListingCase(url=raw_cases[0].url, vin=vin)]
    return [case for case in raw_cases if case.url]


def _candidate_summary(candidate: dict, opportunity: dict | None = None) -> dict:
    opportunity = opportunity or {}
    return {
        "title": candidate.get("title"),
        "source": candidate.get("source"),
        "source_url": candidate.get("source_url"),
        "vin": candidate.get("vin"),
        "asking_price_cad": candidate.get("asking_price_cad"),
        "deal_score": candidate.get("deal_score", opportunity.get("deal_score")),
        "recommendation": candidate.get("recommendation"),
        "image_count": candidate.get("image_count"),
        "missing_data": candidate.get("missing_data") or opportunity.get("missing_key_data") or [],
        "image_risk_reasons": candidate.get("image_risk_reasons") or [],
    }


def _report_summary(report: dict) -> dict:
    report_json = report.get("report_json") or {}
    return {
        "id": report.get("id"),
        "version": report.get("version"),
        "status": report.get("status"),
        "recommendation": report.get("recommendation"),
        "html_url": report.get("html_url"),
        "next_actions": report_json.get("next_actions") or [],
    }


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _finish(exit_code: int, artifact: dict, output_path: str) -> tuple[int, dict]:
    artifact["finished_at"] = _now()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, indent=2, sort_keys=True))
    return exit_code, artifact


def _now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
