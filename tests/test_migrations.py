from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings


def test_alembic_upgrade_head_creates_current_schema(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "migration-smoke.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        config = Config("alembic.ini")
        upgrade(config, "head")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert "search_runs" in table_names
        assert "candidate_snapshots" in table_names
        assert "listings" in table_names
        assert "listing_snapshots" in table_names
        assert "dealer_accounts" in table_names
        assert "opportunity_documents" in table_names
        assert "opportunity_title_evidence" in table_names
        assert "opportunity_recall_compliance_evidence" in table_names
        assert "opportunity_wholesale_evidence" in table_names
        assert "alerts" in table_names
        assert "dealer_corrections" in table_names
        assert "alembic_version" in table_names
        assert "ai_model_outputs" in table_names
        assert "candidate_analyses" in table_names
        assert "image_analyses" in table_names
        assert "lien_profiles" in table_names

        with engine.connect() as connection:
            version = connection.execute(text("select version_num from alembic_version")).scalar_one()
        search_run_columns = {column["name"] for column in inspector.get_columns("search_runs")}
        assert "source_statuses" in search_run_columns
        candidate_columns = {column["name"] for column in inspector.get_columns("candidate_snapshots")}
        assert {"selected", "hidden", "seller_contact_status", "seller_notes"}.issubset(candidate_columns)
        assert "opportunity_id" in candidate_columns
        assert "ai_outputs" in candidate_columns
        listing_columns = {column["name"] for column in inspector.get_columns("listings")}
        assert {"source_name", "source_listing_id", "canonical_url", "active", "dedupe_key"}.issubset(
            listing_columns
        )
        listing_snapshot_columns = {column["name"] for column in inspector.get_columns("listing_snapshots")}
        assert {
            "listing_id",
            "source_name",
            "title",
            "asking_price_cad",
            "mileage_km",
            "location_city",
            "location_province",
            "seller_type",
            "vin",
            "year",
            "make",
            "model",
            "trim",
            "extraction_method",
            "extraction_confidence",
            "extracted_fields",
        }.issubset(listing_snapshot_columns)
        ai_output_columns = {column["name"] for column in inspector.get_columns("ai_model_outputs")}
        assert {
            "feature",
            "subject_type",
            "subject_id",
            "provider",
            "model",
            "model_version",
            "schema_name",
            "schema_version",
            "prompt_hash",
            "input_object_key",
            "output_object_key",
            "parsed_output",
            "validated_output",
            "field_confidences",
            "evidence_links",
            "confidence",
            "status",
            "error_message",
        }.issubset(ai_output_columns)
        opportunity_columns = {column["name"] for column in inspector.get_columns("opportunities")}
        assert "visit_checklist" in opportunity_columns
        feedback_columns = {column["name"] for column in inspector.get_columns("opportunity_feedback")}
        assert {"opportunity_id", "usefulness_rating", "accuracy_rating", "dealer_decision"}.issubset(
            feedback_columns
        )
        history_columns = {column["name"] for column in inspector.get_columns("opportunity_history_profiles")}
        assert {
            "opportunity_id",
            "source_type",
            "title_brand",
            "accident_claims",
            "registration_events",
            "owners_count",
            "odometer_records",
            "service_records",
            "import_history",
            "salvage_status",
            "flood_status",
            "fire_status",
            "theft_status",
        }.issubset(history_columns)
        document_columns = {column["name"] for column in inspector.get_columns("opportunity_documents")}
        assert {
            "opportunity_id",
            "document_type",
            "original_filename",
            "content_type",
            "size_bytes",
            "sha256",
            "object_key",
            "notes",
            "metadata_json",
        }.issubset(document_columns)
        title_columns = {column["name"] for column in inspector.get_columns("opportunity_title_evidence")}
        assert {
            "opportunity_id",
            "source_type",
            "title_clearance_status",
            "provider",
            "lookup_reference",
            "document_id",
            "seller_name",
            "registered_owner_name",
            "ownership_verified",
            "lienholder_name",
            "lien_amount_cad",
            "payout_required",
            "payout_amount_cad",
            "payout_status",
            "notes",
            "raw_payload",
        }.issubset(title_columns)
        recall_columns = {
            column["name"] for column in inspector.get_columns("opportunity_recall_compliance_evidence")
        }
        assert {
            "opportunity_id",
            "source_type",
            "recall_status",
            "compliance_status",
            "provider",
            "lookup_reference",
            "document_id",
            "campaign_number",
            "campaign_description",
            "remedy_status",
            "completion_date",
            "import_country",
            "import_form",
            "riv_case_number",
            "inspection_required",
            "inspection_deadline",
            "notes",
            "raw_payload",
        }.issubset(recall_columns)
        wholesale_columns = {column["name"] for column in inspector.get_columns("opportunity_wholesale_evidence")}
        assert {
            "opportunity_id",
            "source_type",
            "provider",
            "lookup_reference",
            "document_id",
            "region",
            "wholesale_low_cad",
            "wholesale_avg_cad",
            "wholesale_high_cad",
            "trade_in_value_cad",
            "retail_value_cad",
            "auction_sale_low_cad",
            "auction_sale_avg_cad",
            "auction_sale_high_cad",
            "bid_count",
            "bidder_count",
            "high_bid_cad",
            "sale_price_cad",
            "reserve_price_cad",
            "condition_grade",
            "condition_score",
            "buyer_fee_cad",
            "transport_estimate_cad",
            "reconditioning_estimate_cad",
            "notes",
            "raw_payload",
        }.issubset(wholesale_columns)
        alert_columns = {column["name"] for column in inspector.get_columns("alerts")}
        assert {
            "dealer_account_id",
            "search_id",
            "search_run_id",
            "candidate_snapshot_id",
            "opportunity_id",
            "alert_type",
            "title",
            "body",
            "channel",
            "status",
            "recipient_email",
            "sent_at",
            "read_at",
            "metadata_json",
        }.issubset(alert_columns)
        correction_columns = {column["name"] for column in inspector.get_columns("dealer_corrections")}
        assert {
            "dealer_account_id",
            "opportunity_id",
            "entity_type",
            "entity_id",
            "field_name",
            "old_value",
            "new_value",
            "reason",
            "apply_to_future",
        }.issubset(correction_columns)
        candidate_analysis_columns = {column["name"] for column in inspector.get_columns("candidate_analyses")}
        assert {
            "opportunity_id",
            "candidate_snapshot_id",
            "status",
            "selected_reason",
            "score_at_selection",
            "max_images_to_analyze",
            "images_discovered_count",
            "images_analyzed_count",
            "started_at",
            "completed_at",
            "error_summary",
            "analysis_summary",
        }.issubset(candidate_analysis_columns)
        image_analysis_columns = {column["name"] for column in inspector.get_columns("image_analyses")}
        assert {
            "opportunity_id",
            "candidate_analysis_id",
            "candidate_snapshot_id",
            "model_provider",
            "model_name",
            "prompt_version",
            "image_urls",
            "findings",
            "visible_damage",
            "rust_detected",
            "panel_mismatch_detected",
            "tire_wear_concern",
            "risk_adjustment",
            "confidence",
            "raw_payload",
        }.issubset(image_analysis_columns)
        lien_profile_columns = {column["name"] for column in inspector.get_columns("lien_profiles")}
        assert {
            "opportunity_id",
            "title_evidence_id",
            "source_type",
            "lien_status",
            "title_status",
            "evidence_summary",
            "verified",
            "confidence",
            "lienholder_name",
            "lien_amount_cad",
            "payout_required",
            "payout_amount_cad",
            "payout_status",
            "raw_payload",
        }.issubset(lien_profile_columns)
        comparable_columns = {column["name"] for column in inspector.get_columns("comparable_listings")}
        assert "excluded_reason" in comparable_columns

        assert version == "c8a4f2d9e6b1"
    finally:
        get_settings.cache_clear()
