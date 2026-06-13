from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import SellerType


@dataclass(frozen=True)
class SearchFilters:
    query: str | None = None
    make: str | None = None
    model: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    price_min_cad: int | None = None
    price_max_cad: int | None = None
    mileage_max_km: int | None = None
    location_city: str = "Montreal"
    location_province: str = "QC"
    radius_km: int = 50
    seller_type: SellerType = SellerType.UNKNOWN
    limit: int = 25


@dataclass(frozen=True)
class FieldValue:
    value: Any
    confidence: float
    evidence: str | None = None
    method: str = "selector"


@dataclass(frozen=True)
class SourceListingRef:
    source_name: str
    url: str
    source_listing_id: str | None = None
    title: str | None = None
    price_cad: int | None = None
    location: str | None = None


@dataclass(frozen=True)
class SourceSnapshot:
    source_name: str
    url: str
    html: str
    status_code: int | None = None
    rendered: bool = False
    screenshot: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceFailure:
    source_name: str
    reason: str
    url: str | None = None
    message: str | None = None
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedImage:
    url: str
    position: int
    confidence: float = 0.8


@dataclass(frozen=True)
class ParsedListing:
    source_name: str
    url: str
    title: FieldValue | None = None
    asking_price_cad: FieldValue | None = None
    mileage_km: FieldValue | None = None
    location_city: FieldValue | None = None
    location_province: FieldValue | None = None
    year: FieldValue | None = None
    make: FieldValue | None = None
    model: FieldValue | None = None
    trim: FieldValue | None = None
    description: FieldValue | None = None
    seller_type: SellerType = SellerType.UNKNOWN
    images: tuple[ParsedImage, ...] = ()
    extraction_confidence: float = 0.0
    raw_fields: dict[str, Any] = field(default_factory=dict)


class ListingSourceAdapter:
    source_name: str

    async def search(self, filters: SearchFilters) -> list[SourceListingRef]:
        raise NotImplementedError

    async def fetch_search_snapshot(self, filters: SearchFilters) -> SourceSnapshot:
        raise NotImplementedError

    async def fetch_listing(self, ref: SourceListingRef) -> SourceSnapshot:
        raise NotImplementedError

    def parse_search_listings(self, source: str, limit: int = 25) -> list[ParsedListing]:
        raise NotImplementedError

    async def parse_listing(self, snapshot: SourceSnapshot) -> ParsedListing:
        raise NotImplementedError
