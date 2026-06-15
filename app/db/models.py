from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidMixin

JSONType = JSON().with_variant(JSONB, "postgresql")


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
    preferred_brands: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    preferred_models: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
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
    structured_filters: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
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
    extracted_fields: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


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
    field_sources: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class Opportunity(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"

    dealer_account_id: Mapped[str] = mapped_column(ForeignKey("dealer_accounts.id"), nullable=False)
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id"))
    latest_listing_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("listing_snapshots.id"))
    vehicle_profile_id: Mapped[str | None] = mapped_column(ForeignKey("vehicle_profiles.id"))
    stage: Mapped[str] = mapped_column(Text, default="new", nullable=False)
    deal_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    preliminary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    missing_key_data: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    is_overpriced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    candidate_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seller_contact_status: Mapped[str | None] = mapped_column(Text)
    seller_notes: Mapped[str | None] = mapped_column(Text)
    visit_checklist: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class OpportunityHistoryProfile(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_history_profiles"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, default="manual", nullable=False)
    source_name: Mapped[str | None] = mapped_column(Text)
    report_identifier: Mapped[str | None] = mapped_column(Text)
    title_brand: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    accident_claims: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    registration_events: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    owners_count: Mapped[int | None] = mapped_column(Integer)
    odometer_records: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    odometer_issue: Mapped[bool | None] = mapped_column(Boolean)
    service_records_count: Mapped[int | None] = mapped_column(Integer)
    service_records: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    import_history: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    salvage_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    flood_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    fire_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    theft_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class OpportunityDocument(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_documents"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class OpportunityTitleEvidence(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_title_evidence"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, default="manual", nullable=False)
    title_clearance_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    lookup_reference: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("opportunity_documents.id"))
    seller_name: Mapped[str | None] = mapped_column(Text)
    registered_owner_name: Mapped[str | None] = mapped_column(Text)
    ownership_verified: Mapped[bool | None] = mapped_column(Boolean)
    lienholder_name: Mapped[str | None] = mapped_column(Text)
    lien_amount_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    payout_required: Mapped[bool | None] = mapped_column(Boolean)
    payout_amount_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    payout_due_date: Mapped[str | None] = mapped_column(Text)
    payout_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class OpportunityRecallComplianceEvidence(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_recall_compliance_evidence"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, default="manual", nullable=False)
    recall_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    compliance_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    lookup_reference: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("opportunity_documents.id"))
    campaign_number: Mapped[str | None] = mapped_column(Text)
    campaign_description: Mapped[str | None] = mapped_column(Text)
    remedy_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    completion_date: Mapped[str | None] = mapped_column(Text)
    import_country: Mapped[str | None] = mapped_column(Text)
    import_form: Mapped[str | None] = mapped_column(Text)
    riv_case_number: Mapped[str | None] = mapped_column(Text)
    inspection_required: Mapped[bool | None] = mapped_column(Boolean)
    inspection_deadline: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class OpportunityWholesaleEvidence(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_wholesale_evidence"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, default="manual", nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    lookup_reference: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("opportunity_documents.id"))
    region: Mapped[str | None] = mapped_column(Text)
    wholesale_low_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    wholesale_avg_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    wholesale_high_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    trade_in_value_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    retail_value_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    auction_sale_low_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    auction_sale_avg_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    auction_sale_high_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    bid_count: Mapped[int | None] = mapped_column(Integer)
    bidder_count: Mapped[int | None] = mapped_column(Integer)
    high_bid_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    sale_price_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    reserve_price_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    condition_grade: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    condition_score: Mapped[float | None] = mapped_column(Numeric(4, 2))
    condition_notes: Mapped[str | None] = mapped_column(Text)
    buyer_fee_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    transport_estimate_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    reconditioning_estimate_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


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
    excluded_reason: Mapped[str | None] = mapped_column(Text)


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
    calculation_inputs: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class RiskAnalysisModel(UuidMixin, TimestampMixin, Base):
    __tablename__ = "risk_analyses"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    risk_level: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    risk_factors: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    missing_verifications: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)


class DecisionReport(UuidMixin, TimestampMixin, Base):
    __tablename__ = "decision_reports"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    confidence_by_section: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    pdf_object_key: Mapped[str | None] = mapped_column(Text)
    csv_object_key: Mapped[str | None] = mapped_column(Text)


class DealerCorrection(UuidMixin, TimestampMixin, Base):
    __tablename__ = "dealer_corrections"

    dealer_account_id: Mapped[str] = mapped_column(ForeignKey("dealer_accounts.id"), nullable=False)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[object | None] = mapped_column(JSONType)
    new_value: Mapped[object] = mapped_column(JSONType, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    apply_to_future: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OpportunityFeedback(UuidMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_feedback"

    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("decision_reports.id"))
    report_version: Mapped[int | None] = mapped_column(Integer)
    usefulness_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    dealer_decision: Mapped[str] = mapped_column(Text, default="undecided", nullable=False)
    missing_info: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    incorrect_info: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class SearchRun(UuidMixin, TimestampMixin, Base):
    __tablename__ = "search_runs"

    search_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    natural_language_query: Mapped[str | None] = mapped_column(Text)
    structured_filters: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    listing_limit: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="completed", nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_statuses: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class CandidateSnapshot(UuidMixin, TimestampMixin, Base):
    __tablename__ = "candidate_snapshots"

    search_run_id: Mapped[str] = mapped_column(ForeignKey("search_runs.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    listing_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    trim: Mapped[str | None] = mapped_column(Text)
    vin: Mapped[str | None] = mapped_column(Text)
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    body_style: Mapped[str | None] = mapped_column(Text)
    drivetrain: Mapped[str | None] = mapped_column(Text)
    asking_price_cad: Mapped[float | None] = mapped_column(Numeric(12, 2))
    location_city: Mapped[str | None] = mapped_column(Text)
    location_province: Mapped[str | None] = mapped_column(Text)
    seller_type: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    deal_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    is_overpriced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pricing_summary: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    risk_summary: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Numeric(5, 4), default=1.0, nullable=False)
    relevance_reasons: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    image_urls: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    image_risk_adjustment: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    image_risk_reasons: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    confidence_by_section: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seller_contact_status: Mapped[str | None] = mapped_column(Text)
    seller_notes: Mapped[str | None] = mapped_column(Text)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))


class Alert(UuidMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "dealer_account_id",
            "search_id",
            "candidate_snapshot_id",
            "alert_type",
            "channel",
        ),
    )

    dealer_account_id: Mapped[str] = mapped_column(ForeignKey("dealer_accounts.id"), nullable=False)
    search_id: Mapped[str | None] = mapped_column(ForeignKey("searches.id"))
    search_run_id: Mapped[str | None] = mapped_column(ForeignKey("search_runs.id"))
    candidate_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_snapshots.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="unread", nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
