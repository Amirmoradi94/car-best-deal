from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from urllib.parse import urlparse

from app.core.config import Settings
from app.domain.enums import RiskTolerance, SellerType
from app.domain.models import ComparableListing, DealerSettings, ListingSnapshot, ScoredOpportunity, VehicleProfile
from app.scraping.errors import SourceFailureReason, SourceScrapingError
from app.scraping.adapters.autotrader import AutoTraderAdapter
from app.scraping.adapters.kijiji import KijijiAdapter
from app.scraping.contracts import ListingSourceAdapter, ParsedListing, SearchFilters, SourceListingRef
from app.services.image_fetcher import CachedImageFetcher
from app.services.image_risk import DeterministicImageRiskAnalyzer, GeminiImageRiskAnalyzer, ImageRiskResult
from app.scraping.zyte_client import ZyteClient
from app.services.pricing import calculate_pricing, score_and_attach_comparables
from app.services.relevance import infer_search_intent, score_listing_relevance
from app.services.scoring import analyze_risk, score_opportunity
from app.services.vin_analysis import decode_vin, vin_search_filters, vin_target_listing


@dataclass(frozen=True)
class SourceStatus:
    source_name: str
    status: str
    listing_count: int = 0
    url: str | None = None
    reason: str | None = None
    message: str | None = None
    retryable: bool = False
    diagnostics: dict | None = None

    def to_payload(self) -> dict:
        return {
            "source_name": self.source_name,
            "status": self.status,
            "listing_count": self.listing_count,
            "url": self.url,
            "reason": self.reason,
            "message": self.message,
            "retryable": self.retryable,
            "diagnostics": self.diagnostics or {},
        }


@dataclass(frozen=True)
class SourceSearchResult:
    scored_items: list[ScoredOpportunity]
    source_statuses: list[SourceStatus]

    def source_status_payload(self) -> list[dict]:
        return [status.to_payload() for status in self.source_statuses]


class SearchPipeline:
    def __init__(self, settings: Settings | None = None, dealer_settings: DealerSettings | None = None) -> None:
        self.settings = settings or Settings()
        self.dealer_settings = dealer_settings
        self.effective_fixture_mode = self._effective_fixture_mode()
        adapter_settings = self.settings.model_copy(
            update={"scraping_fixture_mode": self.effective_fixture_mode}
        )
        zyte_client = None
        if not self.effective_fixture_mode and self.settings.zyte_api_key:
            zyte_client = ZyteClient(api_key=self.settings.zyte_api_key, api_url=self.settings.zyte_api_url)
        self.kijiji = KijijiAdapter(adapter_settings, zyte_client=zyte_client)
        self.autotrader = AutoTraderAdapter(adapter_settings, zyte_client=zyte_client)
        self.image_risk_analyzer = self._build_image_risk_analyzer()

    async def run_fixture_backed_search(self, filters: SearchFilters):
        return await self.run_multi_source_batch_search(filters)

    async def run_kijiji_batch_search(self, filters: SearchFilters):
        parsed_listings = await self._fetch_source_listings(self.kijiji, filters)
        return self._rank_parsed_listings(parsed_listings, filters, prefix_listing_ids=False)

    async def run_autotrader_batch_search(self, filters: SearchFilters):
        parsed_listings = await self._fetch_source_listings(self.autotrader, filters)
        return self._rank_parsed_listings(parsed_listings, filters, prefix_listing_ids=False)

    async def run_multi_source_batch_search(self, filters: SearchFilters):
        return await self.run_source_batch_search(filters)

    async def run_source_batch_search(
        self,
        filters: SearchFilters,
        sources: tuple[str, ...] | None = None,
    ):
        result = await self.run_source_batch_search_with_statuses(filters, sources=sources)
        return result.scored_items

    async def run_source_batch_search_with_statuses(
        self,
        filters: SearchFilters,
        sources: tuple[str, ...] | None = None,
    ) -> SourceSearchResult:
        parsed_listings: list[ParsedListing] = []
        source_statuses: list[SourceStatus] = []
        adapters = self._adapters_for_sources(sources)
        prefix_listing_ids = len(adapters) > 1
        for adapter in adapters:
            source_result = await self._fetch_source_listings_with_status(adapter, filters)
            parsed_listings.extend(source_result[0])
            source_statuses.append(source_result[1])

        if not parsed_listings and source_statuses and all(status.status == "failed" for status in source_statuses):
            details = ", ".join(
                f"{status.source_name}: {status.reason or status.message or 'failed'}"
                for status in source_statuses
            )
            raise ValueError(f"All selected sources failed ({details}).")

        return SourceSearchResult(
            scored_items=self._rank_parsed_listings(parsed_listings, filters, prefix_listing_ids=prefix_listing_ids),
            source_statuses=source_statuses,
        )

    async def run_previsit_candidate_search(
        self,
        filters: SearchFilters,
        max_candidates: int | None = None,
        sources: tuple[str, ...] | None = None,
    ):
        result = await self.run_previsit_candidate_search_with_statuses(
            filters,
            max_candidates=max_candidates,
            sources=sources,
        )
        return result.scored_items

    async def run_previsit_candidate_search_with_statuses(
        self,
        filters: SearchFilters,
        max_candidates: int | None = None,
        sources: tuple[str, ...] | None = None,
    ) -> SourceSearchResult:
        dealer_settings = self._dealer_settings()
        requested_cap = dealer_settings.max_candidate_count if max_candidates is None else max_candidates
        cap = max(0, min(requested_cap, dealer_settings.max_candidate_count))
        source_result = await self.run_source_batch_search_with_statuses(filters, sources=sources)
        initial_scored = source_result.scored_items
        top_candidates = initial_scored[:cap]
        comparable_pool = [item.listing for item in initial_scored]

        enriched = []
        for candidate in top_candidates:
            enriched_listing = await self._enrich_candidate_listing(candidate.listing, dealer_settings)
            scored_item = self._score_listing(
                enriched_listing,
                comparable_pool,
                dealer_settings,
                candidate.relevance_score,
                candidate.relevance_reasons,
                relevance_penalty_points=0,
            )
            if scored_item:
                enriched.append(scored_item)
        return SourceSearchResult(
            scored_items=sorted(enriched, key=lambda item: item.deal_score, reverse=True),
            source_statuses=source_result.source_statuses,
        )

    async def run_single_listing_analysis(
        self,
        listing_url: str,
        filters: SearchFilters,
        sources: tuple[str, ...] | None = None,
        vin: str | None = None,
    ) -> list[ScoredOpportunity]:
        result = await self.run_single_listing_analysis_with_statuses(
            listing_url,
            filters,
            sources=sources,
            vin=vin,
        )
        return result.scored_items

    async def run_single_listing_analysis_with_statuses(
        self,
        listing_url: str,
        filters: SearchFilters,
        sources: tuple[str, ...] | None = None,
        vin: str | None = None,
    ) -> SourceSearchResult:
        dealer_settings = self._dealer_settings()
        adapter = self._adapter_for_listing_url(listing_url)
        target_listing, target_status = await self._fetch_listing_from_url_with_status(adapter, listing_url)
        if vin:
            target_listing = _apply_vin(target_listing, vin)

        image_risk = await self.image_risk_analyzer.analyze(target_listing, dealer_settings)
        target_listing = _apply_image_risk(target_listing, image_risk)

        comparable_filters = _comparable_filters_for_listing(target_listing, filters)
        comparable_result = await self.run_source_batch_search_with_statuses(comparable_filters, sources=sources)
        comparable_results = comparable_result.scored_items
        comparable_pool = [item.listing for item in comparable_results]
        scored_item = self._score_listing(
            target_listing,
            comparable_pool,
            dealer_settings,
            relevance_score=1.0,
            relevance_reasons=("single_listing_url",),
            relevance_penalty_points=0,
        )
        source_statuses = [target_status, *comparable_result.source_statuses]
        return SourceSearchResult(
            scored_items=[scored_item] if scored_item else [],
            source_statuses=source_statuses,
        )

    async def run_vin_analysis_with_statuses(
        self,
        vin: str,
        filters: SearchFilters,
        sources: tuple[str, ...] | None = None,
    ) -> SourceSearchResult:
        decoded = decode_vin(vin)
        comparable_filters = vin_search_filters(decoded, filters)
        comparable_result = await self.run_source_batch_search_with_statuses(comparable_filters, sources=sources)
        comparable_pool = [item.listing for item in comparable_result.scored_items]
        target_listing = vin_target_listing(decoded, comparable_filters)
        scored_item = self._score_listing(
            target_listing,
            comparable_pool,
            self._dealer_settings(),
            relevance_score=1.0,
            relevance_reasons=("vin_only", "vin_decode_valid"),
            relevance_penalty_points=0,
        )
        exact_matches = [
            item
            for item in comparable_result.scored_items
            if item.listing.vehicle.vin and item.listing.vehicle.vin.upper() == decoded.vin
        ]
        source_statuses = [
            SourceStatus(
                source_name="vin_decode",
                status="ok",
                listing_count=1,
                reason=None,
                message="VIN decoded locally.",
                diagnostics={
                    **self._diagnostics(source_role="vin_decode", fetch_method="local"),
                    "vin": decoded.to_payload(),
                },
            ),
            SourceStatus(
                source_name="vin_source_match",
                status="ok" if exact_matches else "empty",
                listing_count=len(exact_matches),
                reason=None if exact_matches else SourceFailureReason.NO_RESULTS.value,
                message=None if exact_matches else "No marketplace listing with the same VIN was found in parsed results.",
                diagnostics=self._diagnostics(source_role="source_match", fetch_method="local"),
            ),
            SourceStatus(
                source_name="vehicle_history",
                status="blocked",
                reason="not_configured",
                message="Vehicle history integration or document upload is not configured yet.",
                diagnostics=self._diagnostics(source_role="history_check", fetch_method="manual_required"),
            ),
            SourceStatus(
                source_name="lien_title",
                status="blocked",
                reason="not_configured",
                message="Lien/title integration or evidence upload is not configured yet.",
                diagnostics=self._diagnostics(source_role="lien_title_check", fetch_method="manual_required"),
            ),
            SourceStatus(
                source_name="recall",
                status="blocked",
                reason="not_configured",
                message="Recall lookup integration is not configured yet.",
                diagnostics=self._diagnostics(source_role="recall_check", fetch_method="manual_required"),
            ),
            *comparable_result.source_statuses,
        ]
        return SourceSearchResult(
            scored_items=[scored_item] if scored_item else [],
            source_statuses=source_statuses,
        )

    async def _fetch_source_listings(
        self,
        adapter: ListingSourceAdapter,
        filters: SearchFilters,
    ) -> list[ParsedListing]:
        parsed_listings, _status = await self._fetch_source_listings_with_status(adapter, filters)
        return parsed_listings

    async def _fetch_source_listings_with_status(
        self,
        adapter: ListingSourceAdapter,
        filters: SearchFilters,
    ) -> tuple[list[ParsedListing], SourceStatus]:
        try:
            snapshot = await adapter.fetch_search_snapshot(filters)
            parsed_listings = adapter.parse_search_listings(snapshot.html, limit=filters.limit)
        except SourceScrapingError as exc:
            return [], SourceStatus(
                source_name=exc.failure.source_name,
                status="failed",
                listing_count=0,
                url=exc.failure.url or _source_search_url(adapter, filters),
                reason=exc.failure.reason.value,
                message=exc.failure.message,
                retryable=exc.failure.retryable,
                diagnostics=self._diagnostics(
                    source_role="search",
                    fetch_method="zyte" if not self.effective_fixture_mode else "fixture",
                    error_metadata=exc.failure.metadata,
                ),
            )
        except Exception as exc:
            return [], SourceStatus(
                source_name=adapter.source_name,
                status="failed",
                listing_count=0,
                url=_source_search_url(adapter, filters),
                reason=_failure_reason_for_exception(exc).value,
                message=str(exc),
                retryable=False,
                diagnostics=self._diagnostics(
                    source_role="search",
                    fetch_method="zyte" if not self.effective_fixture_mode else "fixture",
                ),
            )

        listing_count = len(parsed_listings)
        return parsed_listings, SourceStatus(
            source_name=adapter.source_name,
            status="ok" if listing_count else "empty",
            listing_count=listing_count,
            url=snapshot.url,
            reason=None if listing_count else SourceFailureReason.NO_RESULTS.value,
            message=None if listing_count else "Source returned no parsed listings.",
            retryable=False,
            diagnostics=self._diagnostics(
                source_role="search",
                fetch_method="fixture" if self.effective_fixture_mode else "zyte",
                status_code=snapshot.status_code,
                rendered=snapshot.rendered,
                parser="search_results",
                snapshot_metadata=snapshot.metadata,
            ),
        )

    async def _fetch_listing_from_url_with_status(
        self,
        adapter: ListingSourceAdapter,
        listing_url: str,
    ) -> tuple[ListingSnapshot, SourceStatus]:
        try:
            listing = await self._fetch_listing_from_url(adapter, listing_url)
        except SourceScrapingError as exc:
            raise ValueError(
                f"{exc.failure.source_name} listing fetch failed: {exc.failure.reason.value}"
            ) from exc
        except Exception as exc:
            raise ValueError(f"{adapter.source_name} listing fetch failed: {exc}") from exc

        return listing, SourceStatus(
            source_name=adapter.source_name,
            status="ok",
            listing_count=1,
            url=listing_url,
            diagnostics=self._diagnostics(
                source_role="target_listing",
                fetch_method="fixture" if self.effective_fixture_mode else "zyte",
                parser="listing_detail",
            ),
        )

    def _rank_parsed_listings(
        self,
        parsed_listings: list[ParsedListing],
        filters: SearchFilters,
        prefix_listing_ids: bool,
    ):
        listing_snapshots = [
            parsed_listing_to_listing_snapshot(
                parsed,
                listing_id=_listing_id_for_parsed(parsed, prefix_listing_ids),
            )
            for parsed in parsed_listings
            if parsed.asking_price_cad is not None and parsed.asking_price_cad.value is not None
        ]
        listing_snapshots = _dedupe_listing_snapshots(listing_snapshots)
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

        dealer_settings = self._dealer_settings()

        scored = []
        for listing in relevant_listings:
            relevance = relevance_by_listing[listing.id]
            scored_item = self._score_listing(
                listing,
                relevant_listings if len(relevant_listings) >= 2 else listing_snapshots,
                dealer_settings,
                relevance.score,
                relevance.reasons,
                relevance.penalty_points,
            )
            if scored_item:
                scored.append(scored_item)
        return sorted(scored, key=lambda item: item.deal_score, reverse=True)

    async def _enrich_candidate_listing(
        self,
        listing: ListingSnapshot,
        dealer_settings: DealerSettings,
    ) -> ListingSnapshot:
        adapter = self._adapter_for_source(listing.source_name)
        snapshot = await adapter.fetch_listing(
            SourceListingRef(
                source_name=listing.source_name,
                url=listing.url,
                source_listing_id=listing.id.split(":", 1)[-1],
            )
        )
        parsed = await adapter.parse_listing(snapshot)
        detail_listing = parsed_listing_to_listing_snapshot(parsed, listing_id=listing.id)
        merged = _merge_listing_snapshot(listing, detail_listing)
        image_risk = await self.image_risk_analyzer.analyze(merged, dealer_settings)
        return _apply_image_risk(merged, image_risk)

    async def _fetch_listing_from_url(
        self,
        adapter: ListingSourceAdapter,
        listing_url: str,
    ) -> ListingSnapshot:
        snapshot = await adapter.fetch_listing(
            SourceListingRef(
                source_name=adapter.source_name,
                url=listing_url,
                source_listing_id=_source_listing_id_from_url(listing_url),
            )
        )
        parsed = await adapter.parse_listing(snapshot)
        return parsed_listing_to_listing_snapshot(
            parsed,
            listing_id=f"{adapter.source_name}:{_source_listing_id_from_url(listing_url)}",
        )

    def _score_listing(
        self,
        listing: ListingSnapshot,
        comparable_pool: list[ListingSnapshot],
        dealer_settings: DealerSettings,
        relevance_score: float,
        relevance_reasons: tuple[str, ...],
        relevance_penalty_points: float,
    ) -> ScoredOpportunity | None:
        same_batch_comparables = [
            listing_snapshot_to_comparable(other)
            for other in comparable_pool
            if other.id != listing.id and other.asking_price_cad is not None
        ]
        if not same_batch_comparables:
            return None
        comparables = score_and_attach_comparables(listing, same_batch_comparables)
        pricing = calculate_pricing(listing, comparables, dealer_settings)
        risk = analyze_risk(listing, dealer_settings)
        scored_item = score_opportunity(listing, pricing, risk, dealer_settings)
        return scored_item.__class__(
            listing=scored_item.listing,
            pricing=scored_item.pricing,
            risk=scored_item.risk,
            deal_score=round(max(0, scored_item.deal_score - relevance_penalty_points), 2),
            recommendation=scored_item.recommendation,
            is_overpriced=scored_item.is_overpriced,
            relevance_score=relevance_score,
            relevance_reasons=relevance_reasons,
            comparables=tuple(comparables),
            confidence_by_section=scored_item.confidence_by_section,
        )

    def _adapter_for_source(self, source_name: str) -> ListingSourceAdapter:
        if source_name == self.kijiji.source_name:
            return self.kijiji
        if source_name == self.autotrader.source_name:
            return self.autotrader
        raise ValueError(f"Unsupported source for enrichment: {source_name}")

    def _adapter_for_listing_url(self, listing_url: str) -> ListingSourceAdapter:
        host = urlparse(listing_url).netloc.casefold()
        if "kijiji.ca" in host:
            return self.kijiji
        if "autotrader.ca" in host:
            return self.autotrader
        raise ValueError(f"Unsupported listing URL source: {listing_url}")

    def _adapters_for_sources(self, sources: tuple[str, ...] | None) -> tuple[ListingSourceAdapter, ...]:
        if not sources:
            return (self.kijiji, self.autotrader)

        adapters = []
        for source in sources:
            adapters.append(self._adapter_for_source(source))
        return tuple(adapters)

    def _dealer_settings(self) -> DealerSettings:
        if self.dealer_settings is not None:
            return self.dealer_settings
        return DealerSettings(
            target_profit_cad=2500,
            risk_tolerance=RiskTolerance.MEDIUM,
            preferred_brands=("Honda", "Toyota"),
            preferred_models=("Civic", "Corolla"),
        )

    def _build_image_risk_analyzer(self):
        fallback = DeterministicImageRiskAnalyzer()
        if (
            self.effective_fixture_mode
            or not self.settings.gemini_image_analysis_enabled
            or not self.settings.gemini_api_key
        ):
            return fallback
        return GeminiImageRiskAnalyzer(
            api_key=self.settings.gemini_api_key,
            api_url=self.settings.gemini_api_url,
            model=self.settings.gemini_model,
            image_fetcher=CachedImageFetcher(
                timeout_seconds=self.settings.image_fetch_timeout_seconds,
                max_bytes=self.settings.image_fetch_max_bytes,
            ),
            fallback_analyzer=fallback,
        )

    def _effective_fixture_mode(self) -> bool:
        if self.settings.app_mode == "fixture":
            return True
        if self.settings.app_mode == "pilot":
            return self.settings.scraping_fixture_mode
        return self.settings.scraping_fixture_mode

    def _diagnostics(
        self,
        *,
        source_role: str,
        fetch_method: str,
        status_code: int | None = None,
        rendered: bool | None = None,
        parser: str | None = None,
        snapshot_metadata: dict | None = None,
        error_metadata: dict | None = None,
    ) -> dict:
        return {
            "app_mode": self.settings.app_mode,
            "fixture_mode": self.effective_fixture_mode,
            "fetch_method": fetch_method,
            "source_role": source_role,
            "status_code": status_code,
            "rendered": bool(rendered),
            "parser": parser,
            "metadata": snapshot_metadata or error_metadata or {},
        }


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
        image_urls=tuple(image.url for image in parsed.images if image.url),
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


def _comparable_filters_for_listing(target: ListingSnapshot, fallback: SearchFilters) -> SearchFilters:
    vehicle = target.vehicle
    query_parts = [vehicle.year, vehicle.make, vehicle.model, target.location_city or fallback.location_city]
    return SearchFilters(
        query=" ".join(str(part) for part in query_parts if part),
        make=vehicle.make or fallback.make,
        model=vehicle.model or fallback.model,
        year_min=vehicle.year or fallback.year_min,
        year_max=vehicle.year or fallback.year_max,
        price_min_cad=fallback.price_min_cad,
        price_max_cad=fallback.price_max_cad,
        mileage_max_km=fallback.mileage_max_km,
        location_city=target.location_city or fallback.location_city,
        location_province=target.location_province or fallback.location_province,
        radius_km=fallback.radius_km,
        seller_type=fallback.seller_type,
        limit=fallback.limit,
    )


def _apply_vin(listing: ListingSnapshot, vin: str) -> ListingSnapshot:
    return replace(
        listing,
        vehicle=replace(listing.vehicle, vin=vin),
    )


def _source_search_url(adapter: ListingSourceAdapter, filters: SearchFilters) -> str | None:
    build_search_url = getattr(adapter, "build_search_url", None)
    if not build_search_url:
        return None
    try:
        return build_search_url(filters)
    except Exception:
        return None


def _failure_reason_for_exception(exc: Exception) -> SourceFailureReason:
    message = str(exc).casefold()
    if "zyte" in message and "required" in message:
        return SourceFailureReason.CREDENTIALS_MISSING
    if "timeout" in message:
        return SourceFailureReason.TIMEOUT
    if "parse" in message or "parsing" in message:
        return SourceFailureReason.PARSING_FAILED
    return SourceFailureReason.UNKNOWN


def _source_listing_id_from_url(listing_url: str) -> str:
    path = urlparse(listing_url).path.strip("/")
    return path.rsplit("/", 1)[-1] or listing_url


def _value(field):
    return field.value if field is not None else None


def _listing_id_for_parsed(parsed: ParsedListing, prefix_listing_ids: bool) -> str:
    raw_id = parsed.raw_fields.get("source_listing_id") or parsed.url
    return f"{parsed.source_name}:{raw_id}" if prefix_listing_ids else raw_id


def _dedupe_listing_snapshots(listings: list[ListingSnapshot]) -> list[ListingSnapshot]:
    deduped: list[ListingSnapshot] = []
    seen: set[tuple[str, str]] = set()
    for listing in listings:
        key = (listing.source_name, listing.url or listing.id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(listing)
    return deduped


def _merge_listing_snapshot(base: ListingSnapshot, detail: ListingSnapshot) -> ListingSnapshot:
    return replace(
        base,
        vehicle=VehicleProfile(
            year=detail.vehicle.year or base.vehicle.year,
            make=detail.vehicle.make or base.vehicle.make,
            model=detail.vehicle.model or base.vehicle.model,
            trim=detail.vehicle.trim or base.vehicle.trim,
            vin=detail.vehicle.vin or base.vehicle.vin,
            mileage_km=detail.vehicle.mileage_km or base.vehicle.mileage_km,
            drivetrain=detail.vehicle.drivetrain or base.vehicle.drivetrain,
            body_style=detail.vehicle.body_style or base.vehicle.body_style,
        ),
        asking_price_cad=detail.asking_price_cad or base.asking_price_cad,
        location_city=detail.location_city or base.location_city,
        location_province=detail.location_province or base.location_province,
        seller_type=detail.seller_type if detail.seller_type != SellerType.UNKNOWN else base.seller_type,
        extraction_confidence=max(base.extraction_confidence, detail.extraction_confidence),
        image_urls=detail.image_urls or base.image_urls,
    )


def _apply_image_risk(listing: ListingSnapshot, image_risk: ImageRiskResult) -> ListingSnapshot:
    return replace(
        listing,
        has_image_risk=True,
        image_risk_adjustment=image_risk.risk_adjustment,
        image_risk_reasons=image_risk.reasons,
        image_urls=listing.image_urls[:image_risk.image_count],
    )
