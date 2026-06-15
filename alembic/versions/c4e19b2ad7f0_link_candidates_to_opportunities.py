"""link candidates to opportunities

Revision ID: c4e19b2ad7f0
Revises: a6d2f7c3b91e
Create Date: 2026-06-13 13:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c4e19b2ad7f0"
down_revision: str | Sequence[str] | None = "a6d2f7c3b91e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("candidate_snapshots") as batch_op:
        batch_op.add_column(sa.Column("opportunity_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_candidate_snapshots_opportunity_id_opportunities",
            "opportunities",
            ["opportunity_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("candidate_snapshots") as batch_op:
        batch_op.drop_constraint(
            "fk_candidate_snapshots_opportunity_id_opportunities",
            type_="foreignkey",
        )
        batch_op.drop_column("opportunity_id")
