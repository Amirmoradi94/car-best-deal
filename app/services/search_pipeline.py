from __future__ import annotations

from app.core.config import Settings
from app.domain.enums import RiskTolerance, SellerType
from app.domain.models import ComparableListing, DealerSettings, ListingSnapshot, VehicleProfile
from app.scraping.adapters.kijiji import KijijiAdapter
from app.scraping.contracts import ParsedListing, SearchFilters
from app.scraping.zyte_client import ZyteClient
from app.services.pricing import calculate_pricing, score_and_attach_comparables
from app.services.relevance import infer_search_intent, score_listing_relevance
from app.services.scoring import analyze_risk, score_opportunity


class SearchPipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        zyte_client = None
        if not self.settings.scraping_fixture_mode and self.settings.zyte_api_key:
            zyte_client = ZyteClient(api_key=self.settings.zyte_api_key, api_url=self.settings.zyte_api_url)
        self.kijiji = KijijiAdapter(self.settings, zyte_client=zyte_client)

    async def run_fixture_backed_search(self, filters: SearchFilters):
        return await self.run_kijiji_batch_search(filters)

    async def run_kijiji_batch_search(self, filters: SearchFilters):
        snapshot = await self.kijiji.fetch_search_snapshot(filters)
        parsed_listings = self.kijiji.parse_search_listings(snapshot.html, limit=filters.limit)
        listing_snapshots = [
            parsed_listing_to_listing_snapshot(
                parsed,
                listing_id=parsed.raw_fields.get("source_listing_id") or parsed.url,
            )
            for parsed in parsed_listings
            if parsed.asking_price_cad is not None and parsed.asking_price_cad.value is not None
        ]
        intent = infer_search_intent(filters)
        relevance_by_listing = {
            listing.id: score_listing_relevance(listing, intent)
            for listing in listing_snapshots
        }
        relevant_listings = [
            listing
            for listing in listing_snapshots
            if relevance_by_listing[listing.id].keep
        ]

        dealer_settings = DealerSettings(
            target_profit_cad=2500,
            risk_tolerance=RiskTolerance.MEDIUM,
            preferred_brands=("Honda", "Toyota"),
            preferred_models=("Civic", "Corolla"),
        )

        scored = []
        for listing in relevant_listings:
            comparable_pool = relevant_listings if len(relevant_listings) >= 2 else listing_snapshots
            same_batch_comparables = [
                listing_snapshot_to_comparable(other)
                for other in comparable_pool
                if other.id != listing.id and other.asking_price_cad is not None
            ]
            if not same_batch_comparables:
                continue
            comparables = score_and_attach_comparables(listing, same_batch_comparables)
            pricing = calculate_pricing(listing, comparables, dealer_settings)
            risk = analyze_risk(listing, dealer_settings)
            scored_item = score_opportunity(listing, pricing, risk, dealer_settings)
            relevance = relevance_by_listing[listing.id]
            scored.append(
                scored_item.__class__(
                    listing=scored_item.listing,
                    pricing=scored_item.pricing,
                    risk=scored_item.risk,
                    deal_score=round(max(0, scored_item.deal_score - relevance.penalty_points), 2),
                    recommendation=scored_item.recommendation,
                    is_overpriced=scored_item.is_overpriced,
                    relevance_score=relevance.score,
                    relevance_reasons=relevance.reasons,
                    confidence_by_section=scored_item.confidence_by_section,
                )
            )
        return sorted(scored, key=lambda item: item.deal_score, reverse=True)


def parsed_listing_to_listing_snapshot(parsed: ParsedListing, listing_id: str) -> ListingSnapshot:
    return ListingSnapshot(
        id=listing_id,
        source_name=parsed.source_name,
        url=parsed.url,
        vehicle=VehicleProfile(
            year=_value(parsed.year),
            make=_value(parsed.make),
            model=_value(parsed.model),
            trim=_value(parsed.trim),
            vin=parsed.raw_fields.get("vin"),
            mileage_km=_value(parsed.mileage_km),
            drivetrain=parsed.raw_fields.get("drivetrain"),
            body_style=parsed.raw_fields.get("body_type"),
        ),
        asking_price_cad=_value(parsed.asking_price_cad),
        location_city=_value(parsed.location_city),
        location_province=_value(parsed.location_province) or "QC",
        seller_type=parsed.seller_type if parsed.seller_type else SellerType.UNKNOWN,
        extraction_confidence=parsed.extraction_confidence,
        has_history=False,
        has_lien_verification=False,
    )


def listing_snapshot_to_comparable(listing: ListingSnapshot) -> ComparableListing:
    return ComparableListing(
        id=listing.id,
        source_name=listing.source_name,
        url=listing.url,
        year=listing.vehicle.year,
        make=listing.vehicle.make,
        model=listing.vehicle.model,
        trim=listing.vehicle.trim,
        mileage_km=listing.vehicle.mileage_km,
        asking_price_cad=listing.asking_price_cad or 0,
        location_city=listing.location_city,
        location_province=listing.location_province,
        seller_type=listing.seller_type,
        drivetrain=listing.vehicle.drivetrain,
        body_style=listing.vehicle.body_style,
        accident_status=listing.accident_status_claim,
    )


def _value(field):
    return field.value if field is not None else None
