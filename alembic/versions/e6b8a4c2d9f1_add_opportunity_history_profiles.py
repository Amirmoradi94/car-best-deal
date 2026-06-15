"""add opportunity history profiles

Revision ID: e6b8a4c2d9f1
Revises: d91d457ddc0f
Create Date: 2026-06-14 10:20:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e6b8a4c2d9f1"
down_revision: str | Sequence[str] | None = "d91d457ddc0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "opportunity_history_profiles",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("report_identifier", sa.Text(), nullable=True),
        sa.Column("title_brand", sa.Text(), nullable=False),
        sa.Column("accident_claims", json_type, nullable=False),
        sa.Column("registration_events", json_type, nullable=False),
        sa.Column("owners_count", sa.Integer(), nullable=True),
        sa.Column("odometer_records", json_type, nullable=False),
        sa.Column("odometer_issue", sa.Boolean(), nullable=True),
        sa.Column("service_records_count", sa.Integer(), nullable=True),
        sa.Column("service_records", json_type, nullable=False),
        sa.Column("import_history", json_type, nullable=False),
        sa.Column("salvage_status", sa.Text(), nullable=False),
        sa.Column("flood_status", sa.Text(), nullable=False),
        sa.Column("fire_status", sa.Text(), nullable=False),
        sa.Column("theft_status", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw_payload", json_type, nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_opportunity_history_profiles_opportunity_created",
        "opportunity_history_profiles",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "idx_opportunity_history_profiles_title_brand",
        "opportunity_history_profiles",
        ["title_brand"],
    )


def downgrade() -> None:
    op.drop_index("idx_opportunity_history_profiles_title_brand", table_name="opportunity_history_profiles")
    op.drop_index(
        "idx_opportunity_history_profiles_opportunity_created",
        table_name="opportunity_history_profiles",
    )
    op.drop_table("opportunity_history_profiles")
