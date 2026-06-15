"""add opportunity title evidence

Revision ID: 3c1fd5a7e2b4
Revises: 92f0d5a3b7c9
Create Date: 2026-06-14 14:15:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "3c1fd5a7e2b4"
down_revision: str | Sequence[str] | None = "92f0d5a3b7c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "opportunity_title_evidence",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("title_clearance_status", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("lookup_reference", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.Text(), nullable=True),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("seller_name", sa.Text(), nullable=True),
        sa.Column("registered_owner_name", sa.Text(), nullable=True),
        sa.Column("ownership_verified", sa.Boolean(), nullable=True),
        sa.Column("lienholder_name", sa.Text(), nullable=True),
        sa.Column("lien_amount_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("payout_required", sa.Boolean(), nullable=True),
        sa.Column("payout_amount_cad", sa.Numeric(12, 2), nullable=True),
        sa.Column("payout_due_date", sa.Text(), nullable=True),
        sa.Column("payout_status", sa.Text(), nullable=False),
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
        "idx_opportunity_title_evidence_opportunity_created",
        "opportunity_title_evidence",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "idx_opportunity_title_evidence_status",
        "opportunity_title_evidence",
        ["title_clearance_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_opportunity_title_evidence_status", table_name="opportunity_title_evidence")
    op.drop_index(
        "idx_opportunity_title_evidence_opportunity_created",
        table_name="opportunity_title_evidence",
    )
    op.drop_table("opportunity_title_evidence")
