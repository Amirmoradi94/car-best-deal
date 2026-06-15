"""add comparable excluded reason

Revision ID: ac4e2d7b9f10
Revises: 9b1d3e5f7a2c
Create Date: 2026-06-15 12:15:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "ac4e2d7b9f10"
down_revision: str | Sequence[str] | None = "9b1d3e5f7a2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("comparable_listings", sa.Column("excluded_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("comparable_listings", "excluded_reason")
