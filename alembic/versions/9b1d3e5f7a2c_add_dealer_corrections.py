"""add dealer corrections

Revision ID: 9b1d3e5f7a2c
Revises: 4c6d8e2a91b7
Create Date: 2026-06-15 11:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9b1d3e5f7a2c"
down_revision: str | Sequence[str] | None = "4c6d8e2a91b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "dealer_corrections",
        sa.Column("dealer_account_id", sa.String(), nullable=False),
        sa.Column("opportunity_id", sa.String(), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("old_value", json_type, nullable=True),
        sa.Column("new_value", json_type, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("apply_to_future", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dealer_account_id"], ["dealer_accounts.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_dealer_corrections_dealer_field",
        "dealer_corrections",
        ["dealer_account_id", "entity_type", "field_name"],
    )
    op.create_index(
        "idx_dealer_corrections_opportunity",
        "dealer_corrections",
        ["opportunity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_dealer_corrections_opportunity", table_name="dealer_corrections")
    op.drop_index("idx_dealer_corrections_dealer_field", table_name="dealer_corrections")
    op.drop_table("dealer_corrections")
