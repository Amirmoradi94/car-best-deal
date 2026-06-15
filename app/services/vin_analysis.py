from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import SellerType
from app.domain.models import ListingSnapshot, VehicleProfile
from app.scraping.contracts import SearchFilters


VIN_LENGTH = 17
INVALID_VIN_CHARS = {"I", "O", "Q"}

TRANSLITERATION = {
    **{str(number): number for number in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}
CHECK_DIGIT_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
YEAR_CODES = {
    "A": 2010,
    "B": 2011,
    "C": 2012,
    "D": 2013,
    "E": 2014,
    "F": 2015,
    "G": 2016,
    "H": 2017,
    "J": 2018,
    "K": 2019,
    "L": 2020,
    "M": 2021,
    "N": 2022,
    "P": 2023,
    "R": 2024,
    "S": 2025,
    "T": 2026,
    "V": 2027,
    "W": 2028,
    "X": 2029,
    "Y": 2030,
    "1": 2031,
    "2": 2032,
    "3": 2033,
    "4": 2034,
    "5": 2035,
    "6": 2036,
    "7": 2037,
    "8": 2038,
    "9": 2039,
}
WMI_MAKES = {
    "1HG": ("Honda", "United States"),
    "2HG": ("Honda", "Canada"),
    "3HG": ("Honda", "Mexico"),
    "JHM": ("Honda", "Japan"),
    "JHL": ("Honda", "Japan"),
    "2HK": ("Honda", "Canada"),
    "1NX": ("Toyota", "United States"),
    "2T1": ("Toyota", "Canada"),
    "4T1": ("Toyota", "United States"),
    "5YF": ("Toyota", "United States"),
    "JTD": ("Toyota", "Japan"),
    "JT2": ("Toyota", "Japan"),
}


@dataclass(frozen=True)
class VinDecode:
    vin: str
    wmi: str
    model_year: int | None
    make: str | None
    country: str | None
    check_digit_valid: bool

    def to_payload(self) -> dict:
        return {
            "vin": self.vin,
            "wmi": self.wmi,
            "model_year": self.model_year,
            "make": self.make,
            "country": self.country,
            "check_digit_valid": self.check_digit_valid,
        }


def decode_vin(vin: str) -> VinDecode:
    normalized = normalize_vin(vin)
    check_digit_valid = _check_digit_valid(normalized)
    if not check_digit_valid:
        raise ValueError("VIN check digit is invalid")

    wmi = normalized[:3]
    make, country = WMI_MAKES.get(wmi, (None, _country_from_first_char(normalized[0])))
    return VinDecode(
        vin=normalized,
        wmi=wmi,
        model_year=YEAR_CODES.get(normalized[9]),
        make=make,
        country=country,
        check_digit_valid=check_digit_valid,
    )


def normalize_vin(vin: str) -> str:
    normalized = "".join(str(vin or "").upper().split())
    if len(normalized) != VIN_LENGTH:
        raise ValueError("VIN must be 17 characters")
    invalid = sorted(set(normalized) & INVALID_VIN_CHARS)
    if invalid:
        raise ValueError(f"VIN contains invalid character(s): {', '.join(invalid)}")
    if any(char not in TRANSLITERATION for char in normalized):
        raise ValueError("VIN contains unsupported characters")
    return normalized


def vin_search_filters(decoded: VinDecode, fallback: SearchFilters) -> SearchFilters:
    year = fallback.year_min or decoded.model_year
    return SearchFilters(
        query=f"{year or ''} {decoded.make or ''} {fallback.model or ''}".strip() or None,
        make=fallback.make or decoded.make,
        model=fallback.model,
        year_min=year,
        year_max=fallback.year_max or year,
        price_min_cad=fallback.price_min_cad,
        price_max_cad=fallback.price_max_cad,
        mileage_max_km=fallback.mileage_max_km,
        location_city=fallback.location_city,
        location_province=fallback.location_province,
        radius_km=fallback.radius_km,
        seller_type=fallback.seller_type,
        limit=fallback.limit,
    )


def vin_target_listing(decoded: VinDecode, filters: SearchFilters) -> ListingSnapshot:
    return ListingSnapshot(
        id=f"vin:{decoded.vin}",
        source_name="vin",
        url=f"vin:{decoded.vin}",
        vehicle=VehicleProfile(
            year=filters.year_min or decoded.model_year,
            make=filters.make or decoded.make,
            model=filters.model,
            trim=None,
            vin=decoded.vin,
        ),
        asking_price_cad=None,
        location_city=filters.location_city,
        location_province=filters.location_province,
        seller_type=SellerType.UNKNOWN,
        extraction_confidence=0.95 if decoded.make or decoded.model_year else 0.7,
        has_history=False,
        has_lien_verification=False,
    )


def _check_digit_valid(vin: str) -> bool:
    total = sum(TRANSLITERATION[char] * weight for char, weight in zip(vin, CHECK_DIGIT_WEIGHTS))
    remainder = total % 11
    expected = "X" if remainder == 10 else str(remainder)
    return vin[8] == expected


def _country_from_first_char(char: str) -> str | None:
    if char in {"1", "4", "5"}:
        return "United States"
    if char == "2":
        return "Canada"
    if char == "3":
        return "Mexico"
    if char == "J":
        return "Japan"
    if char == "K":
        return "South Korea"
    if char == "W":
        return "Germany"
    return None
