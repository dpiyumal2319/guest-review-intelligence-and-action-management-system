"""add content dedupe fields

Revision ID: 202607010003
Revises: 202607010002
Create Date: 2026-07-01 00:03:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607010003"
down_revision: str | None = "202607010002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("records_duplicate_flagged", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "normalized_reviews",
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "normalized_reviews",
        sa.Column("is_content_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table("normalized_reviews") as batch_op:
        batch_op.add_column(sa.Column("duplicate_of_review_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_normalized_reviews_duplicate_of_review_id",
            "normalized_reviews",
            ["duplicate_of_review_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_normalized_reviews_content_hash", "normalized_reviews", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_normalized_reviews_content_hash", table_name="normalized_reviews")
    with op.batch_alter_table("normalized_reviews") as batch_op:
        batch_op.drop_constraint("fk_normalized_reviews_duplicate_of_review_id", type_="foreignkey")
        batch_op.drop_column("duplicate_of_review_id")
    op.drop_column("normalized_reviews", "is_content_duplicate")
    op.drop_column("normalized_reviews", "content_hash")
    op.drop_column("ingestion_runs", "records_duplicate_flagged")
