"""add opportunity wholesale evidence

Revision ID: 8f2b7c9d1a6e
Revises: 6a9c2f1d4e8b
Create Date: 2026-06-15 09:15:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8f2b7c9d1a6e"
down_revision: str | Sequence[str] | None = "6a9c2f1d4e8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "opportunity_wholesale_evidence",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("lookup_reference", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.Text(), nullable=True),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("wholesale_low_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("wholesale_avg_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("wholesale_high_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("trade_in_value_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("retail_value_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("auction_sale_low_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("auction_sale_avg_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("auction_sale_high_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("bid_count", sa.Integer(), nullable=True),
        sa.Column("bidder_count", sa.Integer(), nullable=True),
        sa.Column("high_bid_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("sale_price_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("reserve_price_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("condition_grade", sa.Text(), nullable=False),
        sa.Column("condition_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("condition_notes", sa.Text(), nullable=True),
        sa.Column("buyer_fee_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("transport_estimate_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("reconditioning_estimate_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_payload", json_type, nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["opportunity_documents.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_opportunity_wholesale_evidence_opportunity_created",
        "opportunity_wholesale_evidence",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "idx_opportunity_wholesale_evidence_source",
        "opportunity_wholesale_evidence",
        ["source_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_opportunity_wholesale_evidence_source", table_name="opportunity_wholesale_evidence")
    op.drop_index(
        "idx_opportunity_wholesale_evidence_opportunity_created",
        table_name="opportunity_wholesale_evidence",
    )
    op.drop_table("opportunity_wholesale_evidence")
