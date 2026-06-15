from __future__ import annotations

from app.domain.enums import ConfidenceLevel, Recommendation, RiskTolerance
from app.domain.models import DealerSettings, ListingSnapshot, PricingAnalysis, RiskAnalysis, ScoredOpportunity
from app.services.pricing import clamp


def analyze_risk(listing: ListingSnapshot, settings: DealerSettings) -> RiskAnalysis:
    missing: list[str] = []
    factors: list[str] = []
    risk_score = 0.0

    if not listing.vehicle.vin:
        missing.append("vin")
        risk_score += _missing_data_penalty(listing, settings, base=7)
    if not listing.has_history:
        missing.append("vehicle_history")
        risk_score += _missing_data_penalty(listing, settings, base=10)
    if not listing.has_lien_verification:
        missing.append("lien_verification")
        risk_score += _missing_data_penalty(listing, settings, base=8)

    if listing.accident_status_claim and "accident" in listing.accident_status_claim.casefold():
        factors.append("seller_or_source_mentions_accident")
        risk_score += 12

    for flag in listing.ai_risk_flags:
        factors.append(f"ai_risk_language:{flag}")
        risk_score += _ai_risk_flag_penalty(flag)

    if listing.image_risk_adjustment:
        factors.append("image_analysis_risk_adjustment")
        risk_score += abs(listing.image_risk_adjustment)

    if listing.extraction_confidence < 0.6:
        factors.append("low_listing_extraction_confidence")
        risk_score += 8

    risk_score = clamp(risk_score)
    if risk_score >= 70:
        level = ConfidenceLevel.LOW
    elif risk_score >= 35:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.HIGH

    return RiskAnalysis(
        risk_score=round(risk_score, 2),
        risk_level=level,
        missing_verifications=tuple(missing),
        risk_factors=tuple(factors),
    )


def score_opportunity(
    listing: ListingSnapshot,
    pricing: PricingAnalysis,
    risk: RiskAnalysis,
    settings: DealerSettings,
) -> ScoredOpportunity:
    profit_score = _profit_potential_score(listing, pricing)
    speed_score = _resale_speed_score(listing, settings)
    risk_inverse = 100 - risk.risk_score
    confidence_score = _data_confidence_score(listing, pricing, risk)

    weights = _weights(settings.risk_tolerance)
    deal_score = (
        profit_score * weights["profit"]
        + speed_score * weights["speed"]
        + risk_inverse * weights["risk"]
        + confidence_score * weights["confidence"]
    )
    deal_score = clamp(deal_score + listing.image_risk_adjustment)
    is_overpriced = bool(
        listing.asking_price_cad is not None
        and listing.asking_price_cad > pricing.max_buy_price_cad
    )
    recommendation = _recommendation(deal_score, is_overpriced, risk)

    return ScoredOpportunity(
        listing=listing,
        pricing=pricing,
        risk=risk,
        deal_score=round(deal_score, 2),
        recommendation=recommendation,
        is_overpriced=is_overpriced,
        confidence_by_section={
            "listing": _field_confidence(listing.extraction_confidence),
            "pricing": ConfidenceLevel.HIGH if pricing.comparable_count >= 20 else ConfidenceLevel.MEDIUM,
            "history": ConfidenceLevel.HIGH if listing.has_history else ConfidenceLevel.LOW,
            "images": ConfidenceLevel.MEDIUM if listing.has_image_risk else ConfidenceLevel.UNKNOWN,
            "lien": ConfidenceLevel.HIGH if listing.has_lien_verification else ConfidenceLevel.LOW,
        },
    )


def _missing_data_penalty(listing: ListingSnapshot, settings: DealerSettings, base: float) -> float:
    price = listing.asking_price_cad or 0
    if price >= 30000:
        price_multiplier = 1.5
    elif price >= 18000:
        price_multiplier = 1.25
    else:
        price_multiplier = 1.0

    tolerance_multiplier = {
        RiskTolerance.LOW: 1.35,
        RiskTolerance.MEDIUM: 1.0,
        RiskTolerance.HIGH: 0.75,
    }[settings.risk_tolerance]
    return base * price_multiplier * tolerance_multiplier


def _ai_risk_flag_penalty(flag: str) -> float:
    return {
        "accident_reported": 10,
        "rebuilt_or_salvage": 18,
        "as_is_sale": 12,
        "warning_lights": 10,
        "lien_or_finance": 8,
        "odometer_issue": 14,
    }.get(flag, 4)


def _profit_potential_score(listing: ListingSnapshot, pricing: PricingAnalysis) -> float:
    if listing.asking_price_cad is None:
        return 20

    profit_gap = pricing.max_buy_price_cad - listing.asking_price_cad
    if pricing.max_buy_price_cad <= 0:
        return 0
    return clamp(50 + (profit_gap / pricing.max_buy_price_cad) * 100)


def _resale_speed_score(listing: ListingSnapshot, settings: DealerSettings) -> float:
    score = 55.0
    make = listing.vehicle.make.casefold() if listing.vehicle.make else ""
    model = listing.vehicle.model.casefold() if listing.vehicle.model else ""

    if make and make in {brand.casefold() for brand in settings.preferred_brands}:
        score += 15
    if model and model in {item.casefold() for item in settings.preferred_models}:
        score += 15
    if listing.vehicle.mileage_km and listing.vehicle.mileage_km > 180000:
        score -= 15
    elif listing.vehicle.mileage_km and listing.vehicle.mileage_km < 100000:
        score += 8
    return clamp(score)


def _data_confidence_score(listing: ListingSnapshot, pricing: PricingAnalysis, risk: RiskAnalysis) -> float:
    score = listing.extraction_confidence * 100
    if pricing.preliminary:
        score -= 20
    score -= len(risk.missing_verifications) * 7
    return clamp(score)


def _weights(risk_tolerance: RiskTolerance) -> dict[str, float]:
    if risk_tolerance == RiskTolerance.LOW:
        return {"profit": 0.33, "speed": 0.22, "risk": 0.35, "confidence": 0.10}
    if risk_tolerance == RiskTolerance.HIGH:
        return {"profit": 0.48, "speed": 0.25, "risk": 0.17, "confidence": 0.10}
    return {"profit": 0.40, "speed": 0.25, "risk": 0.25, "confidence": 0.10}


def _recommendation(
    deal_score: float, is_overpriced: bool, risk: RiskAnalysis
) -> Recommendation:
    if risk.risk_score >= 80:
        return Recommendation.PASS
    if is_overpriced:
        return Recommendation.BUY_ONLY_CHEAP
    if deal_score >= 75:
        return Recommendation.BUY
    if deal_score >= 55:
        return Recommendation.BUY_ONLY_CHEAP
    if risk.missing_verifications:
        return Recommendation.NEEDS_MORE_DATA
    return Recommendation.PASS


def _field_confidence(value: float) -> ConfidenceLevel:
    if value >= 0.85:
        return ConfidenceLevel.HIGH
    if value >= 0.6:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW
