"""add opportunity feedback

Revision ID: d91d457ddc0f
Revises: 7d3a2c51a4b8
Create Date: 2026-06-13 16:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d91d457ddc0f"
down_revision: str | Sequence[str] | None = "7d3a2c51a4b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "opportunity_feedback",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("report_id", sa.String(), nullable=True),
        sa.Column("report_version", sa.Integer(), nullable=True),
        sa.Column("usefulness_rating", sa.Integer(), nullable=False),
        sa.Column("accuracy_rating", sa.Integer(), nullable=False),
        sa.Column("dealer_decision", sa.Text(), nullable=False),
        sa.Column("missing_info", json_type, nullable=False),
        sa.Column("incorrect_info", json_type, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["decision_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_opportunity_feedback_opportunity_created",
        "opportunity_feedback",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "idx_opportunity_feedback_decision",
        "opportunity_feedback",
        ["dealer_decision"],
    )


def downgrade() -> None:
    op.drop_index("idx_opportunity_feedback_decision", table_name="opportunity_feedback")
    op.drop_index("idx_opportunity_feedback_opportunity_created", table_name="opportunity_feedback")
    op.drop_table("opportunity_feedback")
