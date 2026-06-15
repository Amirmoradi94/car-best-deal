from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker as SessionMaker

from app.core.config import Settings
from app.db.models import Search
from app.services.saved_searches import saved_search_run_payload
from app.services.search_execution import SearchRunInput, execute_search_run

DEFAULT_SCHEDULE = "daily"


@dataclass(frozen=True)
class ScheduledRefreshItem:
    search_id: str
    name: str
    status: str
    run_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ScheduledRefreshSummary:
    checked_at: datetime
    due_count: int
    refreshed_count: int
    failed_count: int
    items: list[ScheduledRefreshItem]

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at.isoformat(),
            "due_count": self.due_count,
            "refreshed_count": self.refreshed_count,
            "failed_count": self.failed_count,
            "items": [
                {
                    "search_id": item.search_id,
                    "name": item.name,
                    "status": item.status,
                    "run_id": item.run_id,
                    "error_message": item.error_message,
                }
                for item in self.items
            ],
        }


async def execute_scheduled_saved_search_refresh(
    session: Session,
    *,
    settings: Settings,
    now: datetime | None = None,
    limit: int = 25,
) -> ScheduledRefreshSummary:
    checked_at = _aware_datetime(now or datetime.now(UTC))
    due_searches = list_due_saved_searches(
        session,
        now=checked_at,
        default_schedule=settings.saved_search_refresh_default_schedule,
        limit=limit,
    )
    items: list[ScheduledRefreshItem] = []
    for search in due_searches:
        try:
            execution = await execute_search_run(
                search_id=search.id,
                payload=SearchRunInput(**saved_search_run_payload(search)),
                session=session,
                settings=settings,
                saved_search_id=search.id,
            )
        except Exception as exc:  # pragma: no cover - exercised through integration failures.
            session.rollback()
            items.append(
                ScheduledRefreshItem(
                    search_id=search.id,
                    name=search.name,
                    status="failed",
                    error_message=str(exc),
                )
            )
            continue
        items.append(
            ScheduledRefreshItem(
                search_id=search.id,
                name=search.name,
                status="refreshed",
                run_id=execution.run_id,
            )
        )
    return ScheduledRefreshSummary(
        checked_at=checked_at,
        due_count=len(due_searches),
        refreshed_count=sum(1 for item in items if item.status == "refreshed"),
        failed_count=sum(1 for item in items if item.status == "failed"),
        items=items,
    )


def list_due_saved_searches(
    session: Session,
    *,
    now: datetime | None = None,
    default_schedule: str = DEFAULT_SCHEDULE,
    limit: int = 25,
) -> list[Search]:
    checked_at = _aware_datetime(now or datetime.now(UTC))
    scheduled_searches = session.scalars(
        select(Search)
        .where(Search.scheduled.is_(True))
        .order_by(Search.last_run_at.asc().nullsfirst(), Search.created_at.asc())
    )
    due_searches = [
        search
        for search in scheduled_searches
        if is_saved_search_due(search, now=checked_at, default_schedule=default_schedule)
    ]
    return due_searches[:limit]


def is_saved_search_due(
    search: Search,
    *,
    now: datetime | None = None,
    default_schedule: str = DEFAULT_SCHEDULE,
) -> bool:
    if not search.scheduled:
        return False
    interval = schedule_interval(search.schedule_cron or default_schedule)
    checked_at = _aware_datetime(now or datetime.now(UTC))
    last_run_at = _aware_datetime(search.last_run_at) if search.last_run_at else None
    if last_run_at is None:
        return True
    return checked_at - last_run_at >= interval


def validate_refresh_schedule(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    schedule_interval(value)
    return value


def schedule_interval(value: str | None) -> timedelta:
    schedule = (value or DEFAULT_SCHEDULE).strip().lower()
    if schedule == "daily":
        return timedelta(days=1)
    if schedule == "hourly":
        return timedelta(hours=1)
    if schedule.startswith("every:"):
        return _every_interval(schedule.removeprefix("every:"))
    if schedule.startswith("*/"):
        minutes = int(schedule.split(maxsplit=1)[0].removeprefix("*/"))
        if minutes <= 0:
            raise ValueError("Refresh schedule interval must be positive")
        return timedelta(minutes=minutes)
    if schedule.startswith("0 */"):
        hours = int(schedule.split()[1].removeprefix("*/"))
        if hours <= 0:
            raise ValueError("Refresh schedule interval must be positive")
        return timedelta(hours=hours)
    if _is_daily_cron(schedule):
        return timedelta(days=1)
    raise ValueError(
        "Unsupported refresh schedule. Use daily, hourly, every:Nminutes, every:Nhours, */N * * * *, 0 */N * * *, or M H * * *."
    )


async def run_scheduled_saved_search_monitor(
    session_factory: SessionMaker,
    *,
    settings: Settings,
) -> None:
    while True:
        with session_factory() as session:
            await execute_scheduled_saved_search_refresh(
                session,
                settings=settings,
                limit=settings.saved_search_refresh_batch_limit,
            )
        await asyncio.sleep(settings.saved_search_refresh_poll_seconds)


def cancel_monitor_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()


async def wait_for_cancelled_monitor(task: asyncio.Task | None) -> None:
    if task is None:
        return
    with suppress(asyncio.CancelledError):
        await task


def _every_interval(value: str) -> timedelta:
    amount_text = "".join(character for character in value if character.isdigit())
    unit = value.removeprefix(amount_text)
    if not amount_text:
        raise ValueError("Refresh schedule interval must include a number")
    amount = int(amount_text)
    if amount <= 0:
        raise ValueError("Refresh schedule interval must be positive")
    if unit in {"m", "min", "minute", "minutes"}:
        return timedelta(minutes=amount)
    if unit in {"h", "hr", "hour", "hours"}:
        return timedelta(hours=amount)
    if unit in {"d", "day", "days"}:
        return timedelta(days=amount)
    raise ValueError("Refresh schedule unit must be minutes, hours, or days")


def _is_daily_cron(value: str) -> bool:
    parts = value.split()
    if len(parts) != 5:
        return False
    minute, hour, day, month, weekday = parts
    if day != "*" or month != "*" or weekday != "*":
        return False
    return _cron_number(minute, 0, 59) and _cron_number(hour, 0, 23)


def _cron_number(value: str, minimum: int, maximum: int) -> bool:
    if not value.isdigit():
        return False
    parsed = int(value)
    return minimum <= parsed <= maximum


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
