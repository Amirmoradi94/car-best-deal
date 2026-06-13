from __future__ import annotations

import json
from pathlib import Path

from app.domain.enums import RiskTolerance, SellerType
from app.domain.models import ComparableListing, DealerSettings, ListingSnapshot, VehicleProfile
from app.services.pricing import calculate_pricing, score_and_attach_comparables
from app.services.scoring import analyze_risk, score_opportunity


def load_fixture_opportunity(path: Path) -> tuple[ListingSnapshot, list[ComparableListing], DealerSettings]:
    data = json.loads(path.read_text())
    settings_data = data.get("dealer_settings", {})
    settings = DealerSettings(
        target_profit_cad=settings_data.get("target_profit_cad", 2500),
        risk_tolerance=RiskTolerance(settings_data.get("risk_tolerance", "medium")),
        preferred_brands=tuple(settings_data.get("preferred_brands", [])),
        preferred_models=tuple(settings_data.get("preferred_models", [])),
    )

    target = _listing(data["target"])
    comparables = [_comparable(item) for item in data["comparables"]]
    return target, comparables, settings


def score_fixture(path: Path):
    target, comparables, settings = load_fixture_opportunity(path)
    scored_comparables = score_and_attach_comparables(target, comparables)
    pricing = calculate_pricing(target, scored_comparables, settings)
    risk = analyze_risk(target, settings)
    return score_opportunity(target, pricing, risk, settings)


def _vehicle(data: dict) -> VehicleProfile:
    return VehicleProfile(
        year=data.get("year"),
        make=data.get("make"),
        model=data.get("model"),
        trim=data.get("trim"),
        vin=data.get("vin"),
        mileage_km=data.get("mileage_km"),
        drivetrain=data.get("drivetrain"),
        body_style=data.get("body_style"),
    )


def _listing(data: dict) -> ListingSnapshot:
    return ListingSnapshot(
        id=data["id"],
        source_name=data["source_name"],
        url=data["url"],
        vehicle=_vehicle(data["vehicle"]),
        asking_price_cad=data.get("asking_price_cad"),
        location_city=data.get("location_city"),
        location_province=data.get("location_province", "QC"),
        seller_type=SellerType(data.get("seller_type", "unknown")),
        certified=data.get("certified"),
        accident_status_claim=data.get("accident_status_claim"),
        extraction_confidence=data.get("extraction_confidence", 0.8),
        has_history=data.get("has_history", False),
        has_lien_verification=data.get("has_lien_verification", False),
        has_image_risk=data.get("has_image_risk", False),
        image_risk_adjustment=data.get("image_risk_adjustment", 0.0),
    )


def _comparable(data: dict) -> ComparableListing:
    return ComparableListing(
        id=data["id"],
        source_name=data["source_name"],
        url=data["url"],
        year=data.get("year"),
        make=data.get("make"),
        model=data.get("model"),
        trim=data.get("trim"),
        mileage_km=data.get("mileage_km"),
        asking_price_cad=data["asking_price_cad"],
        location_city=data.get("location_city"),
        location_province=data.get("location_province", "QC"),
        seller_type=SellerType(data.get("seller_type", "unknown")),
        certified=data.get("certified"),
        drivetrain=data.get("drivetrain"),
        body_style=data.get("body_style"),
        accident_status=data.get("accident_status"),
    )

