"""add candidate workflow state

Revision ID: a6d2f7c3b91e
Revises: f58b14a774dd
Create Date: 2026-06-13 13:05:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a6d2f7c3b91e"
down_revision: str | Sequence[str] | None = "f58b14a774dd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidate_snapshots",
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "candidate_snapshots",
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("candidate_snapshots", sa.Column("seller_contact_status", sa.Text(), nullable=True))
    op.add_column("candidate_snapshots", sa.Column("seller_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidate_snapshots", "seller_notes")
    op.drop_column("candidate_snapshots", "seller_contact_status")
    op.drop_column("candidate_snapshots", "hidden")
    op.drop_column("candidate_snapshots", "selected")
