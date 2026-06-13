from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.scraping.adapters.kijiji import KijijiAdapter
from app.scraping.contracts import SearchFilters, SourceListingRef
from app.scraping.errors import SourceFailureDetail, SourceFailureReason, SourceScrapingError
from app.scraping.zyte_client import ZyteClient
from app.services.source_snapshot_service import SourceSnapshotPersistence
from app.storage.object_store import LocalObjectStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch and persist Kijiji search/listing snapshots.")
    parser.add_argument("query", nargs="?", default="2020 Honda Civic Montreal")
    parser.add_argument("--url", help="Fetch one listing URL instead of running a search.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--fixture-mode", action="store_true", help="Use local HTML fixtures instead of Zyte.")
    parser.add_argument("--fetch-first-listing", action="store_true", help="Fetch the first listing from search results.")
    parser.add_argument("--save-search-fixture", help="Write fetched search HTML to this fixture path.")
    parser.add_argument("--save-listing-fixture", help="Write fetched listing HTML to this fixture path.")
    parser.add_argument("--object-store-root", help="Override local object store root.")
    return parser


async def run(args: argparse.Namespace) -> dict:
    base_settings = get_settings()
    fixture_mode = bool(args.fixture_mode)
    settings = Settings(
        ZYTE_API_KEY=base_settings.zyte_api_key,
        ZYTE_API_URL=base_settings.zyte_api_url,
        SCRAPING_USE_ZYTE=not fixture_mode,
        SCRAPING_FIXTURE_MODE=fixture_mode,
        OBJECT_STORE_ROOT=args.object_store_root or base_settings.object_store_root,
        SOURCE_SNAPSHOT_RETENTION_DAYS=base_settings.source_snapshot_retention_days,
        GEMINI_MODEL=base_settings.gemini_model,
    )

    zyte_client = None
    if not fixture_mode:
        if not settings.zyte_api_key:
            raise SourceScrapingError(
                SourceFailureDetail(
                    source_name="kijiji",
                    reason=SourceFailureReason.CREDENTIALS_MISSING,
                    message="ZYTE_API_KEY is required for live Kijiji scraping. Use --fixture-mode for local fixtures.",
                    retryable=False,
                )
            )
        zyte_client = ZyteClient(api_key=settings.zyte_api_key, api_url=settings.zyte_api_url)

    adapter = KijijiAdapter(settings=settings, zyte_client=zyte_client)
    store = LocalObjectStore(settings.object_store_root)
    persistence = SourceSnapshotPersistence(store, retention_days=settings.source_snapshot_retention_days)
    result: dict = {"source": "kijiji", "fixture_mode": fixture_mode}

    if args.url:
        listing_snapshot = await adapter.fetch_listing(SourceListingRef(source_name="kijiji", url=args.url))
        persisted = persistence.persist(listing_snapshot)
        parsed = await adapter.parse_listing(listing_snapshot)
        _write_fixture(args.save_listing_fixture, listing_snapshot.html)
        result.update(
            {
                "listing_snapshot": _persisted_payload(persisted),
                "parsed_listing": _parsed_listing_payload(parsed),
            }
        )
        return result

    filters = SearchFilters(query=args.query, limit=args.limit)
    search_snapshot = await adapter.fetch_search_snapshot(filters)
    persisted_search = persistence.persist(search_snapshot)
    refs = adapter.parse_search_results(search_snapshot.html, limit=args.limit)
    _write_fixture(args.save_search_fixture, search_snapshot.html)

    result.update(
        {
            "search_url": search_snapshot.url,
            "search_snapshot": _persisted_payload(persisted_search),
            "listing_refs": [ref.__dict__ for ref in refs],
            "listing_count": len(refs),
        }
    )

    if args.fetch_first_listing and refs:
        listing_snapshot = await adapter.fetch_listing(refs[0])
        persisted_listing = persistence.persist(listing_snapshot)
        parsed = await adapter.parse_listing(listing_snapshot)
        _write_fixture(args.save_listing_fixture, listing_snapshot.html)
        result["first_listing_snapshot"] = _persisted_payload(persisted_listing)
        result["first_parsed_listing"] = _parsed_listing_payload(parsed)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except SourceScrapingError as exc:
        print(
            json.dumps(
                {
                    "error": exc.failure.reason.value,
                    "message": exc.failure.message,
                    "source": exc.failure.source_name,
                    "retryable": exc.failure.retryable,
                },
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0


def _write_fixture(path: str | None, html: str) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html)


def _persisted_payload(snapshot) -> dict:
    return {
        "source_name": snapshot.source_name,
        "source_url": snapshot.source_url,
        "html_object_key": snapshot.html_object_key,
        "metadata_object_key": snapshot.metadata_object_key,
        "screenshot_object_key": snapshot.screenshot_object_key,
        "expires_at": snapshot.expires_at.isoformat(),
        "content_hash": snapshot.content_hash,
    }


def _parsed_listing_payload(parsed) -> dict:
    return {
        "url": parsed.url,
        "title": parsed.title.value if parsed.title else None,
        "asking_price_cad": parsed.asking_price_cad.value if parsed.asking_price_cad else None,
        "mileage_km": parsed.mileage_km.value if parsed.mileage_km else None,
        "location_city": parsed.location_city.value if parsed.location_city else None,
        "location_province": parsed.location_province.value if parsed.location_province else None,
        "year": parsed.year.value if parsed.year else None,
        "make": parsed.make.value if parsed.make else None,
        "model": parsed.model.value if parsed.model else None,
        "trim": parsed.trim.value if parsed.trim else None,
        "image_count": len(parsed.images),
        "extraction_confidence": parsed.extraction_confidence,
    }


if __name__ == "__main__":
    raise SystemExit(main())

