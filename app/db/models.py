from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidMixin


class DealerAccount(UuidMixin, TimestampMixin, Base):
    __tablename__ = "dealer_accounts"

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    dealership_name: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="America/Toronto", nullable=False)
    default_city: Mapped[str | None] = mapped_column(Text, default="Montreal")
    default_province: Mapped[str | None] = mapped_column(Text, default="QC")


class DealerSettingsModel(UuidMixin, TimestampMixin, Base):
    __tablename__ = "dealer_settings"
    __table_args__ = (UniqueConstraint("dealer_account_id"),)

    dealer_account_id: Mapped[str] = mapped_column(ForeignKey("dealer_accounts.id"), nullable=False)
    default_target_profit_cad: Mapped[float] = mapped_column(Numeric(12, 2), default=2500, nullable=False)
    risk_tolerance: Mapped[str] = mapped_column(Text, default="medium", nullable=False)
    preferred_brands: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    preferred_models: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    default_search_radius_km: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    include_overpriced_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    candidate_score_threshold: Mapped[float] = mapped_column(Numeric(5, 2), default=75, nullable=False)
    max_candidate_count: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_images_per_candidate: Mapped[int] = mapped_column(Integer, default=10, nullable=False)


class Search(UuidMixin, TimestampMixin, Base):
    __tablename__ = "searches"

    dealer_account_id: Mapped[str] = mapped_column(ForeignKey("dealer_accounts.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, default="structured", nullable=False)
    natural_language_query: Mapped[str | None] = mapped_column(Text)
    structured_filters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    location_city: Mapped[str | None] = mapped_column(Text)
    location_province: Mapped[str] = mapped_column(Text, default="QC", nullable=False)
    radius_km: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    listing_limit: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    include_overpriced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    target_profit_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    risk_tolerance: Mapped[str | None] = mapped_column(Text)
    scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(Text)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    in_app_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))


class Listing(UuidMixin, TimestampMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("source_name", "canonical_url"),)

    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_listing_id: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(Text)


class ListingSnapshotModel(UuidMixin, TimestampMixin, Base):
    __tablename__ = "listing_snapshots"

    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    asking_price_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    location_city: Mapped[str | None] = mapped_column(Text)
    location_province: Mapped[str | None] = mapped_column(Text)
    seller_type: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    vin: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    trim: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    extracted_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class VehicleProfileModel(UuidMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_profiles"

    vin: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    trim: Mapped[str | None] = mapped_column(Text)
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    canonical_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    identity_status: Mapped[str] = mapped_column(Text, default="partial", nullable=False)
    field_sources: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Opportunity(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"

    dealer_account_id: Mapped[str] = mapped_column(ForeignKey("dealer_accounts.id"), nullable=False)
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id"))
    latest_listing_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("listing_snapshots.id"))
    vehicle_profile_id: Mapped[str | None] = mapped_column(ForeignKey("vehicle_profiles.id"))
    stage: Mapped[str] = mapped_column(Text, default="new", nullable=False)
    deal_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    preliminary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    missing_key_data: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    is_overpriced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    candidate_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seller_contact_status: Mapped[str | None] = mapped_column(Text)
    seller_notes: Mapped[str | None] = mapped_column(Text)


class ComparableListingModel(UuidMixin, TimestampMixin, Base):
    __tablename__ = "comparable_listings"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    trim: Mapped[str | None] = mapped_column(Text)
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    asking_price_cad: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PricingAnalysisModel(UuidMixin, TimestampMixin, Base):
    __tablename__ = "pricing_analyses"
    __table_args__ = (UniqueConstraint("opportunity_id", "version"),)

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="preliminary", nullable=False)
    comparable_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retail_low_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    retail_mid_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    retail_high_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    max_buy_price_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    starting_offer_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    calculation_inputs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class RiskAnalysisModel(UuidMixin, TimestampMixin, Base):
    __tablename__ = "risk_analyses"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    risk_level: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    risk_factors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    missing_verifications: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class DecisionReport(UuidMixin, TimestampMixin, Base):
    __tablename__ = "decision_reports"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence_by_section: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    pdf_object_key: Mapped[str | None] = mapped_column(Text)
    csv_object_key: Mapped[str | None] = mapped_column(Text)

