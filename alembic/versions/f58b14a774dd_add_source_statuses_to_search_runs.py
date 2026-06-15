"""add source statuses to search runs

Revision ID: f58b14a774dd
Revises: bd47890f343e
Create Date: 2026-06-13 12:36:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f58b14a774dd"
down_revision: str | Sequence[str] | None = "bd47890f343e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_runs",
        sa.Column(
            "source_statuses",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("search_runs", "source_statuses")
