from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


MODEL_TO_MAKE = {
    "accord": "Honda",
    "civic": "Honda",
    "cr-v": "Honda",
    "crv": "Honda",
    "fit": "Honda",
    "pilot": "Honda",
    "camry": "Toyota",
    "corolla": "Toyota",
    "highlander": "Toyota",
    "rav4": "Toyota",
    "tacoma": "Toyota",
    "3": "Mazda",
    "cx-3": "Mazda",
    "cx-30": "Mazda",
    "cx-5": "Mazda",
    "cx-50": "Mazda",
    "cx-9": "Mazda",
    "mazda3": "Mazda",
    "elantra": "Hyundai",
    "kona": "Hyundai",
    "santa fe": "Hyundai",
    "sonata": "Hyundai",
    "tucson": "Hyundai",
    "forte": "Kia",
    "rio": "Kia",
    "sorento": "Kia",
    "soul": "Kia",
    "sportage": "Kia",
    "escape": "Ford",
    "f-150": "Ford",
    "f150": "Ford",
    "focus": "Ford",
    "fusion": "Ford",
    "bronco": "Ford",
    "cruze": "Chevrolet",
    "equinox": "Chevrolet",
    "malibu": "Chevrolet",
    "silverado": "Chevrolet",
    "bolt": "Chevrolet",
    "rogue": "Nissan",
    "sentra": "Nissan",
    "altima": "Nissan",
    "qashqai": "Nissan",
    "versa": "Nissan",
    "wrangler": "Jeep",
    "cherokee": "Jeep",
    "grand cherokee": "Jeep",
    "compass": "Jeep",
    "golf": "Volkswagen",
    "jetta": "Volkswagen",
    "tiguan": "Volkswagen",
    "passat": "Volkswagen",
    "impreza": "Subaru",
    "forester": "Subaru",
    "outback": "Subaru",
    "crosstrek": "Subaru",
}

MAKE_ALIASES = {
    "honda": "Honda",
    "toyota": "Toyota",
    "mazda": "Mazda",
    "hyundai": "Hyundai",
    "kia": "Kia",
    "ford": "Ford",
    "chevrolet": "Chevrolet",
    "chevy": "Chevrolet",
    "nissan": "Nissan",
    "jeep": "Jeep",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "subaru": "Subaru",
    "bmw": "BMW",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "audi": "Audi",
}

CITY_ALIASES = {
    "montreal": ("Montreal", "QC"),
    "montréal": ("Montreal", "QC"),
    "laval": ("Laval", "QC"),
    "longueuil": ("Longueuil", "QC"),
    "quebec city": ("Quebec City", "QC"),
    "québec": ("Quebec City", "QC"),
    "toronto": ("Toronto", "ON"),
    "ottawa": ("Ottawa", "ON"),
    "gatineau": ("Gatineau", "QC"),
    "vancouver": ("Vancouver", "BC"),
    "calgary": ("Calgary", "AB"),
    "edmonton": ("Edmonton", "AB"),
    "winnipeg": ("Winnipeg", "MB"),
    "halifax": ("Halifax", "NS"),
}

PROVINCE_ALIASES = {
    "qc": "QC",
    "quebec": "QC",
    "québec": "QC",
    "on": "ON",
    "ontario": "ON",
    "bc": "BC",
    "british columbia": "BC",
    "ab": "AB",
    "alberta": "AB",
    "mb": "MB",
    "manitoba": "MB",
    "ns": "NS",
    "nova scotia": "NS",
    "nb": "NB",
    "new brunswick": "NB",
    "sk": "SK",
    "saskatchewan": "SK",
    "pe": "PE",
    "pei": "PE",
    "nl": "NL",
    "newfoundland": "NL",
}

FILTER_KEYS = {
    "make",
    "model",
    "year_min",
    "year_max",
    "price_min_cad",
    "price_max_cad",
    "mileage_max_km",
    "location_city",
    "location_province",
    "radius_km",
    "seller_type",
}


@dataclass(frozen=True)
class NaturalLanguageInterpretation:
    natural_language_query: str | None
    interpreted_filters: dict[str, Any]
    applied_filters: dict[str, Any]
    confidence: float
    notes: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "natural_language_query": self.natural_language_query,
            "interpreted_filters": self.interpreted_filters,
            "applied_filters": self.applied_filters,
            "interpretation": {
                "confidence": self.confidence,
                "notes": self.notes,
            },
        }


def interpret_natural_language_search(
    natural_language_query: str | None,
    structured_filters: dict[str, Any] | None = None,
) -> NaturalLanguageInterpretation:
    explicit_filters = _clean_filters(structured_filters or {})
    interpreted = _interpret_query(natural_language_query or "")
    applied = merge_interpreted_filters(explicit_filters, interpreted)
    confidence = _confidence(interpreted)
    notes = _notes(interpreted)
    return NaturalLanguageInterpretation(
        natural_language_query=natural_language_query,
        interpreted_filters=interpreted,
        applied_filters=applied,
        confidence=confidence,
        notes=notes,
    )


def merge_interpreted_filters(
    explicit_filters: dict[str, Any],
    interpreted_filters: dict[str, Any],
) -> dict[str, Any]:
    applied = dict(interpreted_filters)
    for key, value in _clean_filters(explicit_filters).items():
        if key in FILTER_KEYS:
            applied[key] = value
    return applied


def _interpret_query(query: str) -> dict[str, Any]:
    normalized = _normalized(query)
    filters: dict[str, Any] = {}
    if not normalized:
        return filters
    filters.update(_year_filters(normalized))
    filters.update(_price_filters(normalized))
    filters.update(_mileage_filters(normalized))
    filters.update(_seller_filter(normalized))
    filters.update(_location_filters(normalized))
    filters.update(_vehicle_filters(normalized))
    return filters


def _year_filters(query: str) -> dict[str, int]:
    filters: dict[str, int] = {}
    range_match = re.search(r"\b((?:19|20)\d{2})\s*(?:-|to|through)\s*((?:19|20)\d{2})\b", query)
    if range_match:
        first = int(range_match.group(1))
        second = int(range_match.group(2))
        filters["year_min"] = min(first, second)
        filters["year_max"] = max(first, second)
        return filters

    newer_match = re.search(r"\b((?:19|20)\d{2})\s*(?:\+|and newer|or newer|plus|up)\b", query)
    if newer_match:
        filters["year_min"] = int(newer_match.group(1))
        return filters

    older_match = re.search(r"\b((?:19|20)\d{2})\s*(?:and older|or older|or less|and earlier)\b", query)
    if older_match:
        filters["year_max"] = int(older_match.group(1))
        return filters

    year_match = re.search(r"\b((?:19|20)\d{2})\b", query)
    if year_match:
        filters["year_min"] = int(year_match.group(1))
    return filters


def _price_filters(query: str) -> dict[str, int]:
    filters: dict[str, int] = {}
    max_match = re.search(
        r"\b(?:under|below|less than|max|maximum|up to)\s*\$?\s*(\d+(?:\.\d+)?)\s*(k|cad|dollars)?\b",
        query,
    )
    if max_match and not _number_followed_by_mileage_unit(query, max_match.end()):
        filters["price_max_cad"] = _money_amount(max_match.group(1), max_match.group(2))
    min_match = re.search(
        r"\b(?:over|above|more than|min|minimum|from)\s*\$?\s*(\d+(?:\.\d+)?)\s*(k|cad|dollars)?\b",
        query,
    )
    if min_match and not _number_followed_by_mileage_unit(query, min_match.end()):
        filters["price_min_cad"] = _money_amount(min_match.group(1), min_match.group(2))
    return filters


def _mileage_filters(query: str) -> dict[str, int]:
    mileage_match = re.search(
        r"\b(?:under|below|less than|max|maximum|up to)\s*(\d+(?:\.\d+)?)\s*(k)?\s*(?:km|kms|kilometers|kilometres)\b",
        query,
    )
    if not mileage_match:
        return {}
    return {"mileage_max_km": _count_amount(mileage_match.group(1), mileage_match.group(2))}


def _seller_filter(query: str) -> dict[str, str]:
    if re.search(r"\b(private|private seller|owner)\b", query):
        return {"seller_type": "private"}
    if re.search(r"\b(dealer|dealership|certified pre-owned|cpo)\b", query):
        return {"seller_type": "dealer"}
    if re.search(r"\b(auction)\b", query):
        return {"seller_type": "auction"}
    return {}


def _location_filters(query: str) -> dict[str, str]:
    filters: dict[str, str] = {}
    for alias in sorted(CITY_ALIASES, key=len, reverse=True):
        if _contains_phrase(query, alias):
            city, province = CITY_ALIASES[alias]
            filters["location_city"] = city
            filters["location_province"] = province
            break
    for alias in sorted(PROVINCE_ALIASES, key=len, reverse=True):
        if _contains_phrase(query, alias):
            filters.setdefault("location_province", PROVINCE_ALIASES[alias])
            break
    return filters


def _vehicle_filters(query: str) -> dict[str, str]:
    filters: dict[str, str] = {}
    for model in sorted(MODEL_TO_MAKE, key=len, reverse=True):
        if _contains_phrase(query, model):
            filters["model"] = _display_model(model)
            filters["make"] = MODEL_TO_MAKE[model]
            return filters
    for alias, make in sorted(MAKE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if _contains_phrase(query, alias):
            filters["make"] = make
            break
    return filters


def _money_amount(amount: str, suffix: str | None) -> int:
    value = float(amount)
    if suffix == "k" or (suffix is None and value < 1000):
        value *= 1000
    return int(round(value))


def _count_amount(amount: str, suffix: str | None) -> int:
    value = float(amount)
    if suffix == "k" or value < 1000:
        value *= 1000
    return int(round(value))


def _display_model(model: str) -> str:
    display = {
        "crv": "CR-V",
        "cr-v": "CR-V",
        "rav4": "RAV4",
        "f150": "F-150",
        "f-150": "F-150",
        "cx-3": "CX-3",
        "cx-30": "CX-30",
        "cx-5": "CX-5",
        "cx-50": "CX-50",
        "cx-9": "CX-9",
        "mazda3": "3",
    }.get(model)
    if display:
        return display
    return " ".join(part.capitalize() for part in model.split())


def _confidence(filters: dict[str, Any]) -> float:
    if not filters:
        return 0.0
    score = 0.35
    if filters.get("make"):
        score += 0.2
    if filters.get("model"):
        score += 0.2
    if filters.get("year_min") or filters.get("year_max"):
        score += 0.1
    if filters.get("price_max_cad") or filters.get("mileage_max_km"):
        score += 0.1
    if filters.get("location_city") or filters.get("location_province"):
        score += 0.05
    return min(round(score, 2), 0.95)


def _notes(filters: dict[str, Any]) -> list[str]:
    if not filters:
        return ["No structured filters could be inferred from the query."]
    notes = []
    for key in sorted(filters):
        notes.append(f"Inferred {key.replace('_', ' ')}.")
    return notes


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in filters.items()
        if key in FILTER_KEYS and value is not None and value != ""
    }


def _contains_phrase(query: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", query) is not None


def _normalized(query: str) -> str:
    return query.casefold().replace(",", " ").replace("/", " ")


def _number_followed_by_mileage_unit(query: str, end_index: int) -> bool:
    return re.match(r"\s*(?:km|kms|kilometers|kilometres)\b", query[end_index:]) is not None
