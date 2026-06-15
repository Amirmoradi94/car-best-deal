"""add alerts

Revision ID: 4c6d8e2a91b7
Revises: 8f2b7c9d1a6e
Create Date: 2026-06-15 10:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4c6d8e2a91b7"
down_revision: str | Sequence[str] | None = "8f2b7c9d1a6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("dealer_account_id", sa.String(), nullable=False),
        sa.Column("search_id", sa.String(), nullable=True),
        sa.Column("search_run_id", sa.String(), nullable=True),
        sa.Column("candidate_snapshot_id", sa.String(), nullable=True),
        sa.Column("opportunity_id", sa.String(), nullable=True),
        sa.Column("alert_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("recipient_email", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", json_type, nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_snapshot_id"], ["candidate_snapshots.id"]),
        sa.ForeignKeyConstraint(["dealer_account_id"], ["dealer_accounts.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
        sa.ForeignKeyConstraint(["search_run_id"], ["search_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dealer_account_id",
            "search_id",
            "candidate_snapshot_id",
            "alert_type",
            "channel",
        ),
    )
    op.create_index("idx_alerts_dealer_status", "alerts", ["dealer_account_id", "status"])
    op.create_index("idx_alerts_search_created", "alerts", ["search_id", "created_at"])
    op.create_index("idx_alerts_candidate", "alerts", ["candidate_snapshot_id"])
    op.create_index("idx_alerts_opportunity", "alerts", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("idx_alerts_opportunity", table_name="alerts")
    op.drop_index("idx_alerts_candidate", table_name="alerts")
    op.drop_index("idx_alerts_search_created", table_name="alerts")
    op.drop_index("idx_alerts_dealer_status", table_name="alerts")
    op.drop_table("alerts")
