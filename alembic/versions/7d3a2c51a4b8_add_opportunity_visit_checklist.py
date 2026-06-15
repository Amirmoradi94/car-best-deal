"""add opportunity visit checklist

Revision ID: 7d3a2c51a4b8
Revises: c4e19b2ad7f0
Create Date: 2026-06-13 15:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7d3a2c51a4b8"
down_revision: str | Sequence[str] | None = "c4e19b2ad7f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.add_column(
            sa.Column("visit_checklist", json_type, nullable=False, server_default=sa.text("'{}'"))
        )
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.alter_column("visit_checklist", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_column("visit_checklist")
