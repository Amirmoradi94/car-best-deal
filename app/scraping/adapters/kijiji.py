from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

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
    first_int,
    extract_json_ld,
    parse_mileage_km,
    parse_money_cad,
    parse_simple_html,
    split_location,
)
from app.scraping.zyte_client import ZyteClient


class KijijiAdapter(ListingSourceAdapter):
    source_name = "kijiji"

    def __init__(
        self,
        settings: Settings,
        zyte_client: ZyteClient | None = None,
        fixture_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.zyte_client = zyte_client
        self.fixture_dir = fixture_dir or Path("fixtures/html/kijiji")

    def build_search_url(self, filters: SearchFilters) -> str:
        terms = filters.query or " ".join(str(part) for part in [filters.year_min, filters.make, filters.model] if part)
        query = {
            "q": terms,
            "ll": filters.location_city,
            "radius": filters.radius_km,
        }
        if filters.price_min_cad is not None:
            query["price_min"] = filters.price_min_cad
        if filters.price_max_cad is not None:
            query["price_max"] = filters.price_max_cad
        return f"https://www.kijiji.ca/b-cars-trucks/{filters.location_city.lower()}/c174l1700281?{urlencode(query)}"

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
        json_ld_refs = self._parse_search_json_ld(source, limit)
        if json_ld_refs:
            return json_ld_refs

        elements = parse_simple_html(source)
        cards = elements_by_attr(elements, "data-testid", "listing-card")
        refs: list[SourceListingRef] = []
        for card in cards[:limit]:
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
        json_ld_listings = self._parse_search_json_ld_listings(source, limit)
        if json_ld_listings:
            return json_ld_listings

        listings: list[ParsedListing] = []
        for ref in self.parse_search_results(source, limit=limit):
            year, make, model, trim = _parse_title_vehicle(ref.title)
            city, province = split_location(ref.location)
            listings.append(
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
                    seller_type=SellerType.UNKNOWN,
                    extraction_confidence=0.65,
                    raw_fields={"source_listing_id": ref.source_listing_id},
                )
            )
        return listings

    def parse_listing_html(self, url: str, source: str) -> ParsedListing:
        json_ld_listing = self._parse_listing_json_ld(url, source)
        if json_ld_listing:
            return json_ld_listing

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
        image_elements = elements_by_class(elements, "vehicle-image")
        images = tuple(
            ParsedImage(url=element.attr("src") or element.attr("data-src") or "", position=index)
            for index, element in enumerate(image_elements)
            if element.attr("src") or element.attr("data-src")
        )

        fields = [
            title,
            price_text,
            mileage_text,
            location_text,
            description,
            trim,
            make,
            model,
        ]
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
            seller_type=SellerType.PRIVATE,
            images=images,
            extraction_confidence=round(confidence, 4),
            raw_fields={
                "title": title,
                "price": price_text,
                "mileage": mileage_text,
                "location": location_text,
                "description": description,
            },
        )

    def _parse_search_json_ld(self, source: str, limit: int) -> list[SourceListingRef]:
        refs: list[SourceListingRef] = []
        for block in extract_json_ld(source):
            if block.get("@type") != "ItemList":
                continue
            for entry in block.get("itemListElement", [])[:limit]:
                item = entry.get("item") if isinstance(entry, dict) else None
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                if not url:
                    continue
                offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
                price = parse_money_cad(str(offers.get("price"))) if offers.get("price") is not None else None
                refs.append(
                    SourceListingRef(
                        source_name=self.source_name,
                        url=url,
                        source_listing_id=url.rstrip("/").split("/")[-1],
                        title=clean_text(item.get("name")),
                        price_cad=price,
                        location=None,
                    )
                )
        return refs

    def _parse_search_json_ld_listings(self, source: str, limit: int) -> list[ParsedListing]:
        listings: list[ParsedListing] = []
        for block in extract_json_ld(source):
            if block.get("@type") != "ItemList":
                continue
            for entry in block.get("itemListElement", [])[:limit]:
                item = entry.get("item") if isinstance(entry, dict) else None
                if not isinstance(item, dict):
                    continue
                parsed = _parsed_listing_from_car(self.source_name, item.get("url") or "", item)
                if parsed:
                    listings.append(parsed)
        return listings

    def _parse_listing_json_ld(self, url: str, source: str) -> ParsedListing | None:
        car = None
        images: list[ParsedImage] = []
        for block in extract_json_ld(source):
            if block.get("@type") == "Car":
                car = block
            elif block.get("@type") == "ItemList":
                for entry in block.get("itemListElement", []):
                    item = entry.get("item") if isinstance(entry, dict) else None
                    if isinstance(item, dict) and item.get("@type") == "Car" and item.get("url") == url:
                        car = item
            elif block.get("@type") == "ImageObject":
                image_url = block.get("contentUrl") or block.get("url")
                if image_url:
                    images.append(ParsedImage(url=image_url, position=len(images), confidence=0.9))

        if not isinstance(car, dict):
            return None
        return _parsed_listing_from_car(self.source_name, url, car, tuple(images))

def _first_text_by_attr(elements, attr: str, value: str) -> str | None:
    matches = elements_by_attr(elements, attr, value)
    return clean_text(matches[0].text) if matches else None


def _field(value, confidence: float, evidence: str | None = None) -> FieldValue | None:
    if value is None:
        return None
    return FieldValue(value=value, confidence=confidence, evidence=evidence or str(value), method="selector")


def _parsed_listing_from_car(
    source_name: str,
    url: str,
    car: dict,
    images: tuple[ParsedImage, ...] = (),
) -> ParsedListing | None:
    if not url:
        return None
    offers = car.get("offers") if isinstance(car.get("offers"), dict) else {}
    mileage = car.get("mileageFromOdometer") if isinstance(car.get("mileageFromOdometer"), dict) else {}
    brand = car.get("brand") if isinstance(car.get("brand"), dict) else {}
    engine = car.get("vehicleEngine") if isinstance(car.get("vehicleEngine"), dict) else {}
    image = car.get("image")
    image_values = list(images)
    if image and not image_values:
        image_values.append(ParsedImage(url=image, position=0, confidence=0.9))

    fields = [
        car.get("name"),
        offers.get("price"),
        mileage.get("value"),
        brand.get("name"),
        car.get("model"),
        car.get("vehicleConfiguration"),
        car.get("description"),
    ]
    confidence = sum(1 for value in fields if value) / len(fields)

    mileage_value = mileage.get("value")
    year_value = car.get("vehicleModelDate")
    title = clean_text(car.get("name"))
    title_year, title_make, title_model, title_trim = _parse_title_vehicle(title)
    structured_model = clean_text(car.get("model"))
    model = title_model if structured_model in (None, "othrmdl") else structured_model
    make = clean_text(brand.get("name")) or title_make
    trim = clean_text(car.get("vehicleConfiguration")) or title_trim
    return ParsedListing(
        source_name=source_name,
        url=url,
        title=_field(title, 0.92),
        asking_price_cad=_field(
            parse_money_cad(str(offers.get("price"))) if offers.get("price") is not None else None,
            0.92,
            str(offers.get("price")) if offers.get("price") is not None else None,
        ),
        mileage_km=_field(
            int(mileage_value) if str(mileage_value or "").isdigit() else None,
            0.9,
            str(mileage_value) if mileage_value is not None else None,
        ),
        location_city=None,
        location_province=_field("QC", 0.5, "inferred from search scope"),
        year=_field(
            int(year_value) if str(year_value or "").isdigit() else title_year,
            0.9,
            str(year_value or title),
        ),
        make=_field(make, 0.9),
        model=_field(model, 0.85),
        trim=_field(trim, 0.85),
        description=_field(clean_text(car.get("description")), 0.85),
        seller_type=SellerType.UNKNOWN,
        images=tuple(image_values),
        extraction_confidence=round(confidence, 4),
        raw_fields={
            "vin": car.get("vehicleIdentificationNumber"),
            "body_type": car.get("bodyType"),
            "color": car.get("color"),
            "fuel_type": engine.get("fuelType"),
            "transmission": car.get("vehicleTransmission"),
            "source_listing_id": url.rstrip("/").split("/")[-1],
        },
    )


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
