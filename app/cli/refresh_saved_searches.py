from __future__ import annotations

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.scheduled_search_refresh import execute_scheduled_saved_search_refresh


def main() -> None:
    parser = argparse.ArgumentParser(description="Run due scheduled saved-search refreshes once.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum due saved searches to refresh.")
    args = parser.parse_args()

    summary = asyncio.run(_run_once(limit=args.limit))
    print(json.dumps(summary, indent=2, sort_keys=True))


async def _run_once(*, limit: int | None) -> dict:
    settings = get_settings()
    init_db()
    with get_session_factory()() as session:
        summary = await execute_scheduled_saved_search_refresh(
            session,
            settings=settings,
            limit=limit or settings.saved_search_refresh_batch_limit,
        )
    return summary.as_dict()


if __name__ == "__main__":
    main()
