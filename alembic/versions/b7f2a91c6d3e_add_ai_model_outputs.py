"""add ai model outputs

Revision ID: b7f2a91c6d3e
Revises: ac4e2d7b9f10
Create Date: 2026-06-15 13:20:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7f2a91c6d3e"
down_revision: str | Sequence[str] | None = "ac4e2d7b9f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ai_model_outputs",
        sa.Column("feature", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("prompt_hash", sa.Text(), nullable=False),
        sa.Column("input_object_key", sa.Text(), nullable=False),
        sa.Column("output_object_key", sa.Text(), nullable=False),
        sa.Column("parsed_output", _json_type(), nullable=False),
        sa.Column("validated_output", _json_type(), nullable=False),
        sa.Column("field_confidences", _json_type(), nullable=False),
        sa.Column("evidence_links", _json_type(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "candidate_snapshots",
        sa.Column("ai_outputs", _json_type(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("candidate_snapshots", "ai_outputs")
    op.drop_table("ai_model_outputs")
