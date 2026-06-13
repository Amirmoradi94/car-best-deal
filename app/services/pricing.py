from __future__ import annotations

from app.domain.enums import SellerType
from app.domain.models import ComparableListing, DealerSettings, ListingSnapshot, PricingAnalysis


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def weighted_percentile(values: list[tuple[float, float]], percentile: float) -> float:
    """Return a weighted percentile from (value, weight) pairs."""
    if not values:
        raise ValueError("weighted_percentile requires at least one value")
    if not 0 <= percentile <= 1:
        raise ValueError("percentile must be between 0 and 1")

    ordered = sorted((value, max(weight, 0.0)) for value, weight in values)
    total_weight = sum(weight for _, weight in ordered)
    if total_weight <= 0:
        midpoint = len(ordered) // 2
        return ordered[midpoint][0]

    threshold = total_weight * percentile
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def comparable_similarity(target: ListingSnapshot, comparable: ComparableListing) -> float:
    vehicle = target.vehicle
    score = 0.0

    if _same(vehicle.make, comparable.make) and _same(vehicle.model, comparable.model):
        score += 25
    elif _same(vehicle.make, comparable.make):
        score += 10

    if vehicle.trim and comparable.trim:
        score += 15 if _same(vehicle.trim, comparable.trim) else 6

    if vehicle.year and comparable.year:
        year_gap = abs(vehicle.year - comparable.year)
        score += max(0, 10 - year_gap * 3)

    if vehicle.mileage_km and comparable.mileage_km:
        mileage_gap = abs(vehicle.mileage_km - comparable.mileage_km)
        score += max(0, 15 - (mileage_gap / 5000))

    if _same(target.location_province, comparable.location_province):
        score += 7
        if _same(target.location_city, comparable.location_city):
            score += 3

    if vehicle.drivetrain and comparable.drivetrain and _same(vehicle.drivetrain, comparable.drivetrain):
        score += 5
    if vehicle.body_style and comparable.body_style and _same(vehicle.body_style, comparable.body_style):
        score += 5

    if target.seller_type == comparable.seller_type:
        score += 3
    if target.certified is not None and target.certified == comparable.certified:
        score += 2

    if comparable.accident_status in (None, "unknown") or target.accident_status_claim in (None, "unknown"):
        score += 5
    elif _same(target.accident_status_claim, comparable.accident_status):
        score += 10

    return round(clamp(score, 0, 100) / 100, 4)


def estimate_retail_range(comparables: list[ComparableListing]) -> tuple[float, float, float]:
    included = [comp for comp in comparables if comp.included]
    if not included:
        raise ValueError("at least one included comparable is required")

    weighted_prices = [
        (comp.asking_price_cad, comp.similarity_score if comp.similarity_score > 0 else 0.01)
        for comp in included
    ]
    return (
        weighted_percentile(weighted_prices, 0.20),
        weighted_percentile(weighted_prices, 0.50),
        weighted_percentile(weighted_prices, 0.80),
    )


def calculate_pricing(
    target: ListingSnapshot,
    comparables: list[ComparableListing],
    settings: DealerSettings,
    estimated_reconditioning_cad: float = 900.0,
    selling_costs_cad: float = 500.0,
    transport_cost_cad: float = 250.0,
    buying_fees_cad: float = 0.0,
    capital_cost_cad: float = 250.0,
    risk_reserve_cad: float = 700.0,
) -> PricingAnalysis:
    retail_low, retail_mid, retail_high = estimate_retail_range(comparables)
    max_buy = (
        retail_mid
        - estimated_reconditioning_cad
        - selling_costs_cad
        - transport_cost_cad
        - buying_fees_cad
        - capital_cost_cad
        - risk_reserve_cad
        - settings.target_profit_cad
    )
    buffer_rate = 0.05 if target.seller_type == SellerType.PRIVATE else 0.02
    starting_offer = max_buy - max_buy * buffer_rate

    return PricingAnalysis(
        retail_low_cad=round(retail_low, 2),
        retail_mid_cad=round(retail_mid, 2),
        retail_high_cad=round(retail_high, 2),
        comparable_count=len([comp for comp in comparables if comp.included]),
        estimated_reconditioning_cad=estimated_reconditioning_cad,
        selling_costs_cad=selling_costs_cad,
        transport_cost_cad=transport_cost_cad,
        buying_fees_cad=buying_fees_cad,
        capital_cost_cad=capital_cost_cad,
        risk_reserve_cad=risk_reserve_cad,
        target_profit_cad=settings.target_profit_cad,
        max_buy_price_cad=round(max_buy, 2),
        starting_offer_cad=round(starting_offer, 2),
        preliminary=not (target.vehicle.vin and target.has_history and target.has_lien_verification),
    )


def score_and_attach_comparables(
    target: ListingSnapshot, comparables: list[ComparableListing]
) -> list[ComparableListing]:
    return [
        ComparableListing(
            **{
                **comp.__dict__,
                "similarity_score": comparable_similarity(target, comp),
            }
        )
        for comp in comparables
    ]


def _same(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    return left.strip().casefold() == right.strip().casefold()

