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
        assert "dealer_accounts" in table_names
        assert "opportunity_documents" in table_names
        assert "opportunity_title_evidence" in table_names
        assert "opportunity_recall_compliance_evidence" in table_names
        assert "opportunity_wholesale_evidence" in table_names
        assert "alerts" in table_names
        assert "dealer_corrections" in table_names
        assert "alembic_version" in table_names

        with engine.connect() as connection:
            version = connection.execute(text("select version_num from alembic_version")).scalar_one()
        search_run_columns = {column["name"] for column in inspector.get_columns("search_runs")}
        assert "source_statuses" in search_run_columns
        candidate_columns = {column["name"] for column in inspector.get_columns("candidate_snapshots")}
        assert {"selected", "hidden", "seller_contact_status", "seller_notes"}.issubset(candidate_columns)
        assert "opportunity_id" in candidate_columns
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
        comparable_columns = {column["name"] for column in inspector.get_columns("comparable_listings")}
        assert "excluded_reason" in comparable_columns

        assert version == "ac4e2d7b9f10"
    finally:
        get_settings.cache_clear()
