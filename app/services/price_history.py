from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Listing, ListingSnapshotModel
from app.domain.models import ScoredOpportunity


@dataclass(frozen=True)
class PriceHistorySummary:
    listing_record_id: str
    latest_listing_snapshot_id: str
    previous_listing_snapshot_id: str | None
    snapshot_count: int
    first_price_cad: float | None
    previous_price_cad: float | None
    current_price_cad: float | None
    lowest_price_cad: float | None
    highest_price_cad: float | None
    price_drop_amount_cad: float | None
    price_drop_percent: float | None
    is_price_drop: bool


def record_listing_price_snapshot(session: Session, scored: ScoredOpportunity) -> PriceHistorySummary:
    listing = _upsert_listing(session, scored)
    prior_snapshots = _listing_snapshots(session, listing.id)
    previous_snapshot = prior_snapshots[-1] if prior_snapshots else None

    snapshot = ListingSnapshotModel(
        listing_id=listing.id,
        source_name=scored.listing.source_name,
        title=_title(scored),
        description=None,
        asking_price_cad=scored.listing.asking_price_cad,
        mileage_km=scored.listing.vehicle.mileage_km,
        location_city=scored.listing.location_city,
        location_province=scored.listing.location_province,
        seller_type=scored.listing.seller_type.value,
        vin=scored.listing.vehicle.vin,
        year=scored.listing.vehicle.year,
        make=scored.listing.vehicle.make,
        model=scored.listing.vehicle.model,
        trim=scored.listing.vehicle.trim,
        extraction_method="search_pipeline",
        extraction_confidence=scored.listing.extraction_confidence,
        extracted_fields={
            "source_listing_id": scored.listing.id,
            "source_url": scored.listing.url,
            "body_style": scored.listing.vehicle.body_style,
            "drivetrain": scored.listing.vehicle.drivetrain,
            "certified": scored.listing.certified,
            "accident_status_claim": scored.listing.accident_status_claim,
        },
    )
    session.add(snapshot)
    session.flush()

    return _price_history_summary(
        listing=listing,
        current_snapshot=snapshot,
        previous_snapshot=previous_snapshot,
        snapshots=[*prior_snapshots, snapshot],
    )


def price_history_payload(summary: PriceHistorySummary) -> dict:
    return {
        "listing_record_id": summary.listing_record_id,
        "latest_listing_snapshot_id": summary.latest_listing_snapshot_id,
        "previous_listing_snapshot_id": summary.previous_listing_snapshot_id,
        "snapshot_count": summary.snapshot_count,
        "first_price_cad": summary.first_price_cad,
        "previous_price_cad": summary.previous_price_cad,
        "current_price_cad": summary.current_price_cad,
        "lowest_price_cad": summary.lowest_price_cad,
        "highest_price_cad": summary.highest_price_cad,
        "price_drop_amount_cad": summary.price_drop_amount_cad,
        "price_drop_percent": summary.price_drop_percent,
        "is_price_drop": summary.is_price_drop,
    }


def _upsert_listing(session: Session, scored: ScoredOpportunity) -> Listing:
    listing = session.scalar(
        select(Listing).where(
            Listing.source_name == scored.listing.source_name,
            Listing.canonical_url == scored.listing.url,
        )
    )
    if listing is None:
        listing = Listing(
            source_name=scored.listing.source_name,
            source_listing_id=scored.listing.id,
            canonical_url=scored.listing.url,
            active=True,
            dedupe_key=_dedupe_key(scored),
        )
    else:
        listing.source_listing_id = scored.listing.id
        listing.active = True
        listing.dedupe_key = listing.dedupe_key or _dedupe_key(scored)
    session.add(listing)
    session.flush()
    return listing


def _listing_snapshots(session: Session, listing_id: str) -> list[ListingSnapshotModel]:
    return list(
        session.scalars(
            select(ListingSnapshotModel)
            .where(ListingSnapshotModel.listing_id == listing_id)
            .order_by(ListingSnapshotModel.created_at.asc(), ListingSnapshotModel.id.asc())
        )
    )


def _price_history_summary(
    *,
    listing: Listing,
    current_snapshot: ListingSnapshotModel,
    previous_snapshot: ListingSnapshotModel | None,
    snapshots: list[ListingSnapshotModel],
) -> PriceHistorySummary:
    current_price = _number(current_snapshot.asking_price_cad)
    previous_price = _number(previous_snapshot.asking_price_cad) if previous_snapshot else None
    prices = [_number(snapshot.asking_price_cad) for snapshot in snapshots]
    known_prices = [price for price in prices if price is not None]
    price_drop_amount = None
    price_drop_percent = None
    is_price_drop = (
        previous_price is not None
        and current_price is not None
        and current_price < previous_price
    )
    if is_price_drop:
        price_drop_amount = round(previous_price - current_price, 2)
        if previous_price > 0:
            price_drop_percent = round((price_drop_amount / previous_price) * 100, 2)

    return PriceHistorySummary(
        listing_record_id=listing.id,
        latest_listing_snapshot_id=current_snapshot.id,
        previous_listing_snapshot_id=previous_snapshot.id if previous_snapshot else None,
        snapshot_count=len(snapshots),
        first_price_cad=known_prices[0] if known_prices else None,
        previous_price_cad=previous_price,
        current_price_cad=current_price,
        lowest_price_cad=min(known_prices) if known_prices else None,
        highest_price_cad=max(known_prices) if known_prices else None,
        price_drop_amount_cad=price_drop_amount,
        price_drop_percent=price_drop_percent,
        is_price_drop=is_price_drop,
    )


def _title(scored: ScoredOpportunity) -> str:
    vehicle = scored.listing.vehicle
    parts = [vehicle.year, vehicle.make, vehicle.model, vehicle.trim]
    return " ".join(str(part) for part in parts if part)


def _dedupe_key(scored: ScoredOpportunity) -> str:
    vehicle = scored.listing.vehicle
    vin_or_listing = vehicle.vin or scored.listing.id
    return f"{scored.listing.source_name}:{vin_or_listing}".lower()


def _number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)

