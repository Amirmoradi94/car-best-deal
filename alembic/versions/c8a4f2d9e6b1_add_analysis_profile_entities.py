"""add analysis profile entities

Revision ID: c8a4f2d9e6b1
Revises: b7f2a91c6d3e
Create Date: 2026-06-15 14:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c8a4f2d9e6b1"
down_revision: str | Sequence[str] | None = "b7f2a91c6d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "candidate_analyses",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("candidate_snapshot_id", sa.String(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("selected_reason", sa.Text(), nullable=True),
        sa.Column("score_at_selection", sa.Numeric(5, 2), nullable=True),
        sa.Column("max_images_to_analyze", sa.Integer(), nullable=False),
        sa.Column("images_discovered_count", sa.Integer(), nullable=False),
        sa.Column("images_analyzed_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("analysis_summary", _json_type(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_snapshot_id"], ["candidate_snapshots.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id", "candidate_snapshot_id"),
    )
    op.create_index("idx_candidate_analyses_opportunity", "candidate_analyses", ["opportunity_id"])
    op.create_index("idx_candidate_analyses_status", "candidate_analyses", ["status"])

    op.create_table(
        "image_analyses",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("candidate_analysis_id", sa.String(), nullable=True),
        sa.Column("candidate_snapshot_id", sa.String(), nullable=True),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("image_urls", _json_type(), nullable=False),
        sa.Column("findings", _json_type(), nullable=False),
        sa.Column("visible_damage", sa.Boolean(), nullable=True),
        sa.Column("rust_detected", sa.Boolean(), nullable=True),
        sa.Column("panel_mismatch_detected", sa.Boolean(), nullable=True),
        sa.Column("tire_wear_concern", sa.Boolean(), nullable=True),
        sa.Column("interior_condition", sa.Text(), nullable=True),
        sa.Column("warning_lights_visible", sa.Boolean(), nullable=True),
        sa.Column("odometer_visible", sa.Boolean(), nullable=True),
        sa.Column("odometer_km", sa.Integer(), nullable=True),
        sa.Column("vin_visible", sa.Boolean(), nullable=True),
        sa.Column("vin", sa.Text(), nullable=True),
        sa.Column("risk_adjustment", sa.Numeric(5, 2), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("raw_payload", _json_type(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_analysis_id"], ["candidate_analyses.id"]),
        sa.ForeignKeyConstraint(["candidate_snapshot_id"], ["candidate_snapshots.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id", "candidate_analysis_id"),
    )
    op.create_index("idx_image_analyses_opportunity", "image_analyses", ["opportunity_id"])

    op.create_table(
        "lien_profiles",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("title_evidence_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("lien_status", sa.Text(), nullable=False),
        sa.Column("title_status", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("lienholder_name", sa.Text(), nullable=True),
        sa.Column("lien_amount_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("payout_required", sa.Boolean(), nullable=True),
        sa.Column("payout_amount_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("payout_status", sa.Text(), nullable=False),
        sa.Column("raw_payload", _json_type(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["title_evidence_id"], ["opportunity_title_evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_lien_profiles_opportunity", "lien_profiles", ["opportunity_id"])
    op.create_index("idx_lien_profiles_title_evidence", "lien_profiles", ["title_evidence_id"])


def downgrade() -> None:
    op.drop_index("idx_lien_profiles_title_evidence", table_name="lien_profiles")
    op.drop_index("idx_lien_profiles_opportunity", table_name="lien_profiles")
    op.drop_table("lien_profiles")
    op.drop_index("idx_image_analyses_opportunity", table_name="image_analyses")
    op.drop_table("image_analyses")
    op.drop_index("idx_candidate_analyses_status", table_name="candidate_analyses")
    op.drop_index("idx_candidate_analyses_opportunity", table_name="candidate_analyses")
    op.drop_table("candidate_analyses")

