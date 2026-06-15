from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DealerAccount, Search

DEFAULT_DEALER_EMAIL = "local-dealer@example.test"

RUN_OPTION_KEYS = {
    "_sources",
    "_max_candidates",
    "_listing_url",
    "_vin",
}


def create_saved_search(
    session: Session,
    *,
    name: str,
    natural_language_query: str | None,
    structured_filters: dict[str, Any],
    listing_limit: int,
    sources: str,
    max_candidates: int,
    listing_url: str | None = None,
    vin: str | None = None,
    include_overpriced: bool = False,
    scheduled: bool = False,
    schedule_cron: str | None = None,
    alerts_enabled: bool = False,
    email_alerts_enabled: bool = False,
    in_app_alerts_enabled: bool = True,
) -> Search:
    dealer = get_or_create_default_dealer(session)
    filters = _stored_filters(
        structured_filters,
        sources=sources,
        max_candidates=max_candidates,
        listing_url=listing_url,
        vin=vin,
    )
    search = Search(
        dealer_account_id=dealer.id,
        name=name,
        mode=_search_mode(
            listing_url=listing_url,
            vin=vin,
            natural_language_query=natural_language_query,
        ),
        natural_language_query=natural_language_query,
        structured_filters=filters,
        location_city=structured_filters.get("location_city") or "Montreal",
        location_province=structured_filters.get("location_province") or "QC",
        radius_km=structured_filters.get("radius_km") or 50,
        listing_limit=listing_limit,
        include_overpriced=include_overpriced,
        scheduled=scheduled,
        schedule_cron=schedule_cron or ("daily" if scheduled else None),
        alerts_enabled=alerts_enabled,
        email_alerts_enabled=email_alerts_enabled,
        in_app_alerts_enabled=in_app_alerts_enabled,
    )
    session.add(search)
    session.commit()
    session.refresh(search)
    return search


def list_saved_searches(session: Session, limit: int = 50) -> list[Search]:
    return list(
        session.scalars(
            select(Search)
            .order_by(Search.created_at.desc())
            .limit(limit)
        )
    )


def get_saved_search(session: Session, search_id: str) -> Search | None:
    return session.get(Search, search_id)


def mark_saved_search_ran(session: Session, search_id: str) -> None:
    search = get_saved_search(session, search_id)
    if search is None:
        return
    search.last_run_at = datetime.now(UTC)
    session.add(search)
    session.commit()


def update_saved_search_schedule(
    session: Session,
    search_id: str,
    *,
    scheduled: bool | None = None,
    schedule_cron: str | None = None,
    alerts_enabled: bool | None = None,
    email_alerts_enabled: bool | None = None,
    in_app_alerts_enabled: bool | None = None,
) -> Search | None:
    search = get_saved_search(session, search_id)
    if search is None:
        return None
    if scheduled is not None:
        search.scheduled = scheduled
        search.schedule_cron = schedule_cron or ("daily" if scheduled else None)
    elif schedule_cron is not None:
        search.schedule_cron = schedule_cron
    if alerts_enabled is not None:
        search.alerts_enabled = alerts_enabled
    if email_alerts_enabled is not None:
        search.email_alerts_enabled = email_alerts_enabled
    if in_app_alerts_enabled is not None:
        search.in_app_alerts_enabled = in_app_alerts_enabled
    session.add(search)
    session.commit()
    session.refresh(search)
    return search


def saved_search_payload(search: Search) -> dict:
    filters = dict(search.structured_filters or {})
    return {
        "id": search.id,
        "name": search.name,
        "mode": search.mode,
        "natural_language_query": search.natural_language_query,
        "structured_filters": _public_filters(filters),
        "listing_limit": search.listing_limit,
        "sources": filters.get("_sources", "both"),
        "max_candidates": filters.get("_max_candidates", 50),
        "listing_url": filters.get("_listing_url"),
        "vin": filters.get("_vin"),
        "include_overpriced": search.include_overpriced,
        "scheduled": search.scheduled,
        "schedule_cron": search.schedule_cron,
        "alerts_enabled": search.alerts_enabled,
        "email_alerts_enabled": search.email_alerts_enabled,
        "in_app_alerts_enabled": search.in_app_alerts_enabled,
        "location_city": search.location_city,
        "location_province": search.location_province,
        "radius_km": search.radius_km,
        "last_run_at": search.last_run_at.isoformat() if search.last_run_at else None,
        "created_at": search.created_at.isoformat() if search.created_at else None,
        "updated_at": search.updated_at.isoformat() if search.updated_at else None,
    }


def saved_search_run_payload(search: Search) -> dict:
    filters = dict(search.structured_filters or {})
    public_filters = _public_filters(filters)
    public_filters.setdefault("location_city", search.location_city)
    public_filters.setdefault("location_province", search.location_province)
    public_filters.setdefault("radius_km", search.radius_km)
    return {
        "name": search.name,
        "natural_language_query": search.natural_language_query,
        "structured_filters": public_filters,
        "listing_limit": search.listing_limit,
        "sources": filters.get("_sources", "both"),
        "max_candidates": filters.get("_max_candidates", 50),
        "listing_url": filters.get("_listing_url"),
        "vin": filters.get("_vin"),
    }


def get_or_create_default_dealer(session: Session) -> DealerAccount:
    dealer = session.scalar(
        select(DealerAccount).where(DealerAccount.email == DEFAULT_DEALER_EMAIL)
    )
    if dealer is not None:
        return dealer
    dealer = DealerAccount(
        email=DEFAULT_DEALER_EMAIL,
        display_name="Local Dealer",
        dealership_name="Local Dealer",
        default_city="Montreal",
        default_province="QC",
    )
    session.add(dealer)
    session.flush()
    return dealer


def _stored_filters(
    structured_filters: dict[str, Any],
    *,
    sources: str,
    max_candidates: int,
    listing_url: str | None,
    vin: str | None,
) -> dict:
    filters = {
        key: _json_value(value)
        for key, value in structured_filters.items()
        if value is not None
    }
    filters["_sources"] = sources
    filters["_max_candidates"] = max_candidates
    if listing_url:
        filters["_listing_url"] = listing_url
    if vin:
        filters["_vin"] = vin
    return filters


def _search_mode(*, listing_url: str | None, vin: str | None, natural_language_query: str | None) -> str:
    if listing_url:
        return "single_listing"
    if vin:
        return "vin"
    if natural_language_query:
        return "natural_language"
    return "structured"


def _public_filters(filters: dict[str, Any]) -> dict:
    return {
        key: value
        for key, value in filters.items()
        if key not in RUN_OPTION_KEYS and value is not None
    }


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value"):
        return value.value
    return value
