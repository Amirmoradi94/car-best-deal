"""add opportunity recall compliance evidence

Revision ID: 6a9c2f1d4e8b
Revises: 3c1fd5a7e2b4
Create Date: 2026-06-14 15:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6a9c2f1d4e8b"
down_revision: str | Sequence[str] | None = "3c1fd5a7e2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "opportunity_recall_compliance_evidence",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("recall_status", sa.Text(), nullable=False),
        sa.Column("compliance_status", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("lookup_reference", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.Text(), nullable=True),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("campaign_number", sa.Text(), nullable=True),
        sa.Column("campaign_description", sa.Text(), nullable=True),
        sa.Column("remedy_status", sa.Text(), nullable=False),
        sa.Column("completion_date", sa.Text(), nullable=True),
        sa.Column("import_country", sa.Text(), nullable=True),
        sa.Column("import_form", sa.Text(), nullable=True),
        sa.Column("riv_case_number", sa.Text(), nullable=True),
        sa.Column("inspection_required", sa.Boolean(), nullable=True),
        sa.Column("inspection_deadline", sa.Text(), nullable=True),
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
        "idx_opportunity_recall_compliance_opportunity_created",
        "opportunity_recall_compliance_evidence",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "idx_opportunity_recall_compliance_recall_status",
        "opportunity_recall_compliance_evidence",
        ["recall_status"],
    )
    op.create_index(
        "idx_opportunity_recall_compliance_compliance_status",
        "opportunity_recall_compliance_evidence",
        ["compliance_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_opportunity_recall_compliance_compliance_status",
        table_name="opportunity_recall_compliance_evidence",
    )
    op.drop_index(
        "idx_opportunity_recall_compliance_recall_status",
        table_name="opportunity_recall_compliance_evidence",
    )
    op.drop_index(
        "idx_opportunity_recall_compliance_opportunity_created",
        table_name="opportunity_recall_compliance_evidence",
    )
    op.drop_table("opportunity_recall_compliance_evidence")
