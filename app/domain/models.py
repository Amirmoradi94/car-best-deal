from dataclasses import dataclass, field

from app.domain.enums import ConfidenceLevel, Recommendation, RiskTolerance, SellerType


@dataclass(frozen=True)
class DealerSettings:
    target_profit_cad: float = 2500.0
    risk_tolerance: RiskTolerance = RiskTolerance.MEDIUM
    preferred_brands: tuple[str, ...] = ()
    preferred_models: tuple[str, ...] = ()
    candidate_score_threshold: float = 75.0
    max_candidate_count: int = 50
    max_images_per_candidate: int = 10


@dataclass(frozen=True)
class VehicleProfile:
    year: int | None
    make: str | None
    model: str | None
    trim: str | None = None
    vin: str | None = None
    mileage_km: int | None = None
    drivetrain: str | None = None
    body_style: str | None = None


@dataclass(frozen=True)
class ListingSnapshot:
    id: str
    source_name: str
    url: str
    vehicle: VehicleProfile
    asking_price_cad: float | None
    location_city: str | None = None
    location_province: str | None = "QC"
    seller_type: SellerType = SellerType.UNKNOWN
    certified: bool | None = None
    accident_status_claim: str | None = None
    extraction_confidence: float = 0.8
    has_history: bool = False
    has_lien_verification: bool = False
    has_image_risk: bool = False
    image_risk_adjustment: float = 0.0


@dataclass(frozen=True)
class ComparableListing:
    id: str
    source_name: str
    url: str
    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    mileage_km: int | None
    asking_price_cad: float
    location_city: str | None = None
    location_province: str | None = "QC"
    seller_type: SellerType = SellerType.UNKNOWN
    certified: bool | None = None
    drivetrain: str | None = None
    body_style: str | None = None
    accident_status: str | None = None
    similarity_score: float = 0.0
    included: bool = True


@dataclass(frozen=True)
class PricingAnalysis:
    retail_low_cad: float
    retail_mid_cad: float
    retail_high_cad: float
    comparable_count: int
    estimated_reconditioning_cad: float
    selling_costs_cad: float
    transport_cost_cad: float
    buying_fees_cad: float
    capital_cost_cad: float
    risk_reserve_cad: float
    target_profit_cad: float
    max_buy_price_cad: float
    starting_offer_cad: float
    preliminary: bool


@dataclass(frozen=True)
class RiskAnalysis:
    risk_score: float
    risk_level: ConfidenceLevel
    missing_verifications: tuple[str, ...] = ()
    risk_factors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoredOpportunity:
    listing: ListingSnapshot
    pricing: PricingAnalysis
    risk: RiskAnalysis
    deal_score: float
    recommendation: Recommendation
    is_overpriced: bool
    relevance_score: float = 1.0
    relevance_reasons: tuple[str, ...] = ()
    confidence_by_section: dict[str, ConfidenceLevel] = field(default_factory=dict)
