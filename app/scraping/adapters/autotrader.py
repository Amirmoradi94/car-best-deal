from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urlencode

from app.core.config import Settings
from app.domain.enums import SellerType
from app.scraping.contracts import (
    FieldValue,
    ListingSourceAdapter,
    ParsedImage,
    ParsedListing,
    SearchFilters,
    SourceListingRef,
    SourceSnapshot,
)
from app.scraping.parser_utils import (
    clean_text,
    elements_by_attr,
    elements_by_class,
    extract_json_ld,
    first_int,
    parse_mileage_km,
    parse_money_cad,
    parse_simple_html,
    split_location,
)
from app.scraping.zyte_client import ZyteClient


class AutoTraderAdapter(ListingSourceAdapter):
    source_name = "autotrader"

    def __init__(
        self,
        settings: Settings,
        zyte_client: ZyteClient | None = None,
        fixture_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.zyte_client = zyte_client
        self.fixture_dir = fixture_dir or Path("fixtures/html/autotrader")

    def build_search_url(self, filters: SearchFilters) -> str:
        make = filters.make or _query_part(filters.query, 1) or "honda"
        model = filters.model or _query_part(filters.query, 2) or "civic"
        city = filters.location_city or "Montreal"
        province = "quebec" if filters.location_province == "QC" else filters.location_province.lower()
        query = {
            "rcp": filters.limit,
            "rcs": 0,
            "srt": 35,
            "prx": filters.radius_km,
            "loc": f"{city}, QC",
        }
        if filters.year_min or filters.year_max:
            query["yRng"] = f"{filters.year_min or ''},{filters.year_max or filters.year_min or ''}"
        if filters.price_min_cad or filters.price_max_cad:
            query["prv"] = f"{filters.price_min_cad or ''},{filters.price_max_cad or ''}"
        return (
            "https://www.autotrader.ca/cars/"
            f"{quote_plus(make.lower())}/{quote_plus(model.lower())}/qc/{quote_plus(city.lower())}/"
            f"?{urlencode(query)}"
        )

    async def search(self, filters: SearchFilters) -> list[SourceListingRef]:
        snapshot = await self.fetch_search_snapshot(filters)
        return self.parse_search_results(snapshot.html, limit=filters.limit)

    async def fetch_search_snapshot(self, filters: SearchFilters) -> SourceSnapshot:
        if self.settings.scraping_fixture_mode:
            html = (self.fixture_dir / "search_results.html").read_text()
            return SourceSnapshot(source_name=self.source_name, url=self.build_search_url(filters), html=html)
        if not self.zyte_client:
            raise RuntimeError("Zyte client is required when fixture mode is disabled")
        result = await self.zyte_client.fetch_browser_html(self.build_search_url(filters))
        return SourceSnapshot(
            source_name=self.source_name,
            url=result.url,
            html=result.html,
            status_code=result.status_code,
            rendered=result.rendered,
        )

    async def fetch_listing(self, ref: SourceListingRef) -> SourceSnapshot:
        if self.settings.scraping_fixture_mode:
            html = (self.fixture_dir / "listing_detail.html").read_text()
            return SourceSnapshot(source_name=self.source_name, url=ref.url, html=html)
        if not self.zyte_client:
            raise RuntimeError("Zyte client is required when fixture mode is disabled")
        result = await self.zyte_client.fetch_browser_html(ref.url)
        return SourceSnapshot(
            source_name=self.source_name,
            url=result.url,
            html=result.html,
            status_code=result.status_code,
            rendered=result.rendered,
        )

    async def parse_listing(self, snapshot: SourceSnapshot) -> ParsedListing:
        return self.parse_listing_html(snapshot.url, snapshot.html)

    def parse_search_results(self, source: str, limit: int = 25) -> list[SourceListingRef]:
        refs = self._parse_json_ld_refs(source, limit)
        if refs:
            return refs
        refs = self._parse_next_data_refs(source, limit)
        if refs:
            return refs
        refs = []
        for card in elements_by_attr(parse_simple_html(source), "data-testid", "listing-card")[:limit]:
            url = card.attr("data-url")
            if not url:
                continue
            refs.append(
                SourceListingRef(
                    source_name=self.source_name,
                    url=url,
                    source_listing_id=card.attr("data-listing-id"),
                    title=clean_text(card.attr("data-title") or card.text),
                    price_cad=parse_money_cad(card.attr("data-price")),
                    location=clean_text(card.attr("data-location")),
                )
            )
        return refs

    def parse_search_listings(self, source: str, limit: int = 25) -> list[ParsedListing]:
        listings = self._parse_json_ld_listings(source, limit)
        if listings:
            return listings
        listings = self._parse_next_data_listings(source, limit)
        if listings:
            return listings
        parsed = []
        for ref in self.parse_search_results(source, limit=limit):
            year, make, model, trim = _parse_title_vehicle(ref.title)
            city, province = split_location(ref.location)
            parsed.append(
                ParsedListing(
                    source_name=self.source_name,
                    url=ref.url,
                    title=_field(ref.title, 0.78),
                    asking_price_cad=_field(ref.price_cad, 0.72, str(ref.price_cad) if ref.price_cad else None),
                    location_city=_field(city, 0.65, ref.location),
                    location_province=_field(province, 0.65, ref.location),
                    year=_field(year, 0.7, ref.title),
                    make=_field(make, 0.65, ref.title),
                    model=_field(model, 0.65, ref.title),
                    trim=_field(trim, 0.55, ref.title),
                    seller_type=SellerType.DEALER,
                    extraction_confidence=0.65,
                    raw_fields={"source_listing_id": ref.source_listing_id},
                )
            )
        return parsed

    def parse_listing_html(self, url: str, source: str) -> ParsedListing:
        next_data_listing = self._parse_next_data_listing_detail(url, source)
        if next_data_listing:
            return next_data_listing

        json_listing = self._parse_json_ld_listing(url, source)
        if json_listing:
            return json_listing

        elements = parse_simple_html(source)
        title = _first_text_by_attr(elements, "data-testid", "listing-title")
        price_text = _first_text_by_attr(elements, "data-testid", "price")
        mileage_text = _first_text_by_attr(elements, "data-testid", "mileage")
        location_text = _first_text_by_attr(elements, "data-testid", "location")
        description = _first_text_by_attr(elements, "data-testid", "description")
        trim = _first_text_by_attr(elements, "data-testid", "trim")
        make = _first_text_by_attr(elements, "data-testid", "make")
        model = _first_text_by_attr(elements, "data-testid", "model")
        city, province = split_location(location_text)
        images = tuple(
            ParsedImage(url=element.attr("src") or element.attr("data-src") or "", position=index)
            for index, element in enumerate(elements_by_class(elements, "vehicle-image"))
            if element.attr("src") or element.attr("data-src")
        )
        fields = [title, price_text, mileage_text, location_text, description, trim, make, model]
        confidence = sum(1 for value in fields if value) / len(fields)
        return ParsedListing(
            source_name=self.source_name,
            url=url,
            title=_field(title, 0.92),
            asking_price_cad=_field(parse_money_cad(price_text), 0.9, price_text),
            mileage_km=_field(parse_mileage_km(mileage_text), 0.88, mileage_text),
            location_city=_field(city, 0.85, location_text),
            location_province=_field(province, 0.85, location_text),
            year=_field(first_int(title), 0.75, title),
            make=_field(make, 0.9),
            model=_field(model, 0.9),
            trim=_field(trim, 0.82),
            description=_field(description, 0.8),
            seller_type=SellerType.DEALER,
            images=images,
            extraction_confidence=round(confidence, 4),
            raw_fields={},
        )

    def _parse_json_ld_refs(self, source: str, limit: int) -> list[SourceListingRef]:
        refs: list[SourceListingRef] = []
        for listing in self._json_ld_vehicle_items(source)[:limit]:
            url = listing.get("url")
            if not url:
                continue
            offers = listing.get("offers") if isinstance(listing.get("offers"), dict) else {}
            refs.append(
                SourceListingRef(
                    source_name=self.source_name,
                    url=url,
                    source_listing_id=url.rstrip("/").split("/")[-1],
                    title=clean_text(listing.get("name")),
                    price_cad=parse_money_cad(str(offers.get("price"))) if offers.get("price") is not None else None,
                    location=None,
                )
            )
        return refs

    def _parse_json_ld_listings(self, source: str, limit: int) -> list[ParsedListing]:
        parsed: list[ParsedListing] = []
        for item in self._json_ld_vehicle_items(source)[:limit]:
            listing = _parsed_listing_from_vehicle(self.source_name, item.get("url") or "", item)
            if listing:
                parsed.append(listing)
        return parsed

    def _parse_json_ld_listing(self, url: str, source: str) -> ParsedListing | None:
        for item in self._json_ld_vehicle_items(source):
            item_url = item.get("url")
            if not item_url or item_url == url or url.rstrip("/") in item_url.rstrip("/"):
                parsed = _parsed_listing_from_vehicle(self.source_name, url or item_url or "", item)
                if parsed:
                    return parsed
        return None

    def _json_ld_vehicle_items(self, source: str) -> list[dict]:
        items: list[dict] = []
        for block in extract_json_ld(source):
            block_type = block.get("@type")
            if block_type in {"Car", "Vehicle", "Product"}:
                items.append(block)
            for entry in block.get("itemListElement", []) if isinstance(block.get("itemListElement"), list) else []:
                item = entry.get("item") if isinstance(entry, dict) else None
                if isinstance(item, dict):
                    item_type = item.get("@type")
                    if item_type in {"Car", "Vehicle", "Product"} or item.get("offers"):
                        items.append(item)
        return items

    def _parse_next_data_refs(self, source: str, limit: int) -> list[SourceListingRef]:
        refs: list[SourceListingRef] = []
        for listing in _next_data_listing_items(source)[:limit]:
            url = listing.get("url")
            if not isinstance(url, str) or not url:
                continue
            refs.append(
                SourceListingRef(
                    source_name=self.source_name,
                    url=url,
                    source_listing_id=_next_data_listing_id(listing),
                    title=_next_data_listing_title(listing),
                    price_cad=_next_data_listing_price(listing),
                    location=_next_data_listing_location_text(listing),
                )
            )
        return refs

    def _parse_next_data_listings(self, source: str, limit: int) -> list[ParsedListing]:
        parsed: list[ParsedListing] = []
        for listing in _next_data_listing_items(source)[:limit]:
            parsed_listing = _parsed_listing_from_next_data(self.source_name, listing)
            if parsed_listing:
                parsed.append(parsed_listing)
        return parsed

    def _parse_next_data_listing_detail(self, url: str, source: str) -> ParsedListing | None:
        listing = _next_data_listing_detail(source)
        if not listing:
            return None
        return _parsed_listing_from_next_data(self.source_name, listing, url_override=url)


def _first_text_by_attr(elements, attr: str, value: str) -> str | None:
    matches = elements_by_attr(elements, attr, value)
    return clean_text(matches[0].text) if matches else None


def _field(value, confidence: float, evidence: str | None = None) -> FieldValue | None:
    if value is None:
        return None
    return FieldValue(value=value, confidence=confidence, evidence=evidence or str(value), method="selector")


def _parsed_listing_from_vehicle(source_name: str, url: str, item: dict) -> ParsedListing | None:
    if not url:
        return None
    offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
    brand = item.get("brand") if isinstance(item.get("brand"), dict) else {}
    mileage = item.get("mileageFromOdometer") if isinstance(item.get("mileageFromOdometer"), dict) else {}
    image = item.get("image")
    title = clean_text(item.get("name"))
    title_year, title_make, title_model, title_trim = _parse_title_vehicle(title)
    make = clean_text(brand.get("name") if isinstance(brand, dict) else item.get("brand")) or title_make
    model = clean_text(item.get("model")) or title_model
    trim = clean_text(item.get("vehicleConfiguration") or item.get("sku")) or title_trim
    year_value = item.get("vehicleModelDate") or item.get("modelDate") or title_year
    mileage_value = mileage.get("value") or item.get("mileage")
    price_value = offers.get("price") or item.get("price")

    fields = [title, price_value, mileage_value, make, model, trim]
    confidence = sum(1 for value in fields if value) / len(fields)
    return ParsedListing(
        source_name=source_name,
        url=url,
        title=_field(title, 0.9),
        asking_price_cad=_field(parse_money_cad(str(price_value)) if price_value is not None else None, 0.88, str(price_value) if price_value is not None else None),
        mileage_km=_field(_intish(mileage_value), 0.82, str(mileage_value) if mileage_value is not None else None),
        location_city=None,
        location_province=_field("QC", 0.45, "inferred from search scope"),
        year=_field(_intish(year_value) or title_year, 0.85, str(year_value or title)),
        make=_field(make, 0.85),
        model=_field(model, 0.82),
        trim=_field(trim, 0.7),
        description=_field(clean_text(item.get("description")), 0.75),
        seller_type=SellerType.DEALER,
        images=(ParsedImage(url=image, position=0, confidence=0.85),) if isinstance(image, str) else (),
        extraction_confidence=round(confidence, 4),
        raw_fields={"source_listing_id": url.rstrip("/").split("/")[-1]},
    )


def _next_data_listing_items(source: str) -> list[dict]:
    data = _extract_next_data(source)
    if not data:
        return []
    page_props = data.get("props", {}).get("pageProps", {})
    listings = page_props.get("listings")
    if isinstance(listings, list):
        return [listing for listing in listings if isinstance(listing, dict)]
    return []


def _next_data_listing_detail(source: str) -> dict | None:
    data = _extract_next_data(source)
    if not data:
        return None
    listing = data.get("props", {}).get("pageProps", {}).get("listingDetails")
    return listing if isinstance(listing, dict) else None


def _extract_next_data(source: str) -> dict | None:
    match = re.search(
        r'<script id=["\']__NEXT_DATA__["\'] type=["\']application/json["\']>(.*?)</script>',
        source,
        flags=re.I | re.S,
    )
    if not match:
        return None
    for raw in (match.group(1).strip(), html.unescape(match.group(1).strip())):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else None
    return None


def _parsed_listing_from_next_data(
    source_name: str,
    item: dict,
    url_override: str | None = None,
) -> ParsedListing | None:
    url = url_override or item.get("url")
    if not isinstance(url, str) or not url:
        return None
    vehicle = item.get("vehicle") if isinstance(item.get("vehicle"), dict) else {}
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    dealer = seller.get("dealer") if isinstance(seller.get("dealer"), dict) else {}

    make = clean_text(vehicle.get("make"))
    model = clean_text(vehicle.get("model"))
    trim = clean_text(vehicle.get("modelVersionInput") or vehicle.get("variant") or vehicle.get("subtitle"))
    year = _intish(vehicle.get("modelYear"))
    title = _next_data_listing_title(item)
    price = _next_data_listing_price(item)
    mileage = _intish(vehicle.get("mileageInKmRaw")) or parse_mileage_km(str(vehicle.get("mileageInKm") or ""))
    city = clean_text(location.get("city"))
    province = clean_text(location.get("provinceCode") or dealer.get("region"))
    description = clean_text(item.get("description"))
    seller_type = _seller_type_from_next_data(seller)
    images = tuple(
        ParsedImage(url=image_url, position=index, confidence=0.9)
        for index, image_url in enumerate(item.get("images", [])[:10])
        if isinstance(image_url, str) and image_url
    )

    fields = [title, price, mileage, make, model, trim, year, city, province]
    confidence = sum(1 for value in fields if value is not None) / len(fields)
    return ParsedListing(
        source_name=source_name,
        url=url,
        title=_field(title, 0.92),
        asking_price_cad=_field(price, 0.9, str(price) if price is not None else None),
        mileage_km=_field(mileage, 0.88, str(vehicle.get("mileageInKm") or "")),
        location_city=_field(city, 0.86),
        location_province=_field(province, 0.86),
        year=_field(year, 0.9, str(year) if year is not None else None),
        make=_field(make, 0.9),
        model=_field(model, 0.9),
        trim=_field(trim, 0.82),
        description=_field(description, 0.75),
        seller_type=seller_type,
        images=images,
        extraction_confidence=round(confidence, 4),
        raw_fields={
            "source_listing_id": _next_data_listing_id(item),
            "seller_id": seller.get("id"),
            "seller_name": seller.get("companyName"),
            "transmission": vehicle.get("transmission") or vehicle.get("transmissionType"),
            "drivetrain": vehicle.get("driveTrain"),
            "body_type": vehicle.get("bodyType") or vehicle.get("variant"),
            "fuel": vehicle.get("fuel") or _formatted_nested_value(vehicle.get("fuelCategory")),
            "external_customer_id": item.get("externalCustomerId"),
        },
    )


def _next_data_listing_title(item: dict) -> str | None:
    vehicle = item.get("vehicle") if isinstance(item.get("vehicle"), dict) else {}
    parts = [
        vehicle.get("modelYear"),
        vehicle.get("make"),
        vehicle.get("model"),
        vehicle.get("modelVersionInput") or vehicle.get("variant") or vehicle.get("subtitle"),
    ]
    title = clean_text(" ".join(str(part) for part in parts if part))
    return title or clean_text(item.get("title"))


def _next_data_listing_price(item: dict) -> int | None:
    prices = item.get("prices") if isinstance(item.get("prices"), dict) else {}
    public_price = prices.get("public") if isinstance(prices.get("public"), dict) else {}
    if public_price.get("priceRaw") is not None:
        return _intish(public_price.get("priceRaw"))
    price = item.get("price") if isinstance(item.get("price"), dict) else {}
    return parse_money_cad(str(price.get("priceFormatted") or price.get("price") or ""))


def _next_data_listing_id(item: dict) -> str | None:
    value = item.get("id") or item.get("identifier") or item.get("crossReferenceId")
    return str(value) if value else None


def _next_data_listing_location_text(item: dict) -> str | None:
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    city = clean_text(location.get("city"))
    province = clean_text(location.get("provinceCode"))
    return ", ".join(part for part in (city, province) if part) or None


def _seller_type_from_next_data(seller: dict) -> SellerType:
    seller_type = str(seller.get("type") or "").casefold()
    if "dealer" in seller_type:
        return SellerType.DEALER
    if "private" in seller_type:
        return SellerType.PRIVATE
    return SellerType.UNKNOWN


def _formatted_nested_value(value) -> str | None:
    if isinstance(value, dict):
        return clean_text(value.get("formatted") or value.get("raw"))
    return clean_text(value)


def _parse_title_vehicle(title: str | None) -> tuple[int | None, str | None, str | None, str | None]:
    if not title:
        return None, None, None, None
    parts = title.split()
    year = first_int(title)
    if year and parts and parts[0] == str(year):
        parts = parts[1:]
    make = parts[0] if len(parts) >= 1 else None
    model = parts[1] if len(parts) >= 2 else None
    trim = " ".join(parts[2:]) if len(parts) >= 3 else None
    return year, make, model, trim


def _query_part(query: str | None, index: int) -> str | None:
    if not query:
        return None
    parts = [part for part in re.findall(r"[A-Za-z0-9]+", query) if not part.isdigit()]
    return parts[index - 1] if len(parts) >= index else None


def _intish(value) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return int(digits) if digits else None
