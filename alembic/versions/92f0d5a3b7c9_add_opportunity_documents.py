"""add opportunity documents

Revision ID: 92f0d5a3b7c9
Revises: e6b8a4c2d9f1
Create Date: 2026-06-14 13:35:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "92f0d5a3b7c9"
down_revision: str | Sequence[str] | None = "e6b8a4c2d9f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "opportunity_documents",
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", json_type, nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "idx_opportunity_documents_opportunity_created",
        "opportunity_documents",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "idx_opportunity_documents_type",
        "opportunity_documents",
        ["document_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_opportunity_documents_type", table_name="opportunity_documents")
    op.drop_index(
        "idx_opportunity_documents_opportunity_created",
        table_name="opportunity_documents",
    )
    op.drop_table("opportunity_documents")
