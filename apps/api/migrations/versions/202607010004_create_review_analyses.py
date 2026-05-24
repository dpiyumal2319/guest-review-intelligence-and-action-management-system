"""create review analyses

Revision ID: 202607010004
Revises: 202607010003
Create Date: 2026-07-01 00:04:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607010004"
down_revision: str | None = "202607010003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_analyses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "review_id",
            sa.Integer(),
            sa.ForeignKey("normalized_reviews.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("sentiment_label", sa.String(length=32), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(5, 3), nullable=False),
        sa.Column("sentiment_confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "issue_category_code",
            sa.String(length=64),
            sa.ForeignKey("issue_categories.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("severity_score", sa.Integer(), nullable=False),
        sa.Column("severity_label", sa.String(length=32), nullable=False),
        sa.Column(
            "department_code",
            sa.String(length=64),
            sa.ForeignKey("departments.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("analysis_version", sa.String(length=64), nullable=False),
        sa.Column("explanation_factors", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_review_analyses_active_review", "review_analyses", ["review_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_review_analyses_active_review", table_name="review_analyses")
    op.drop_table("review_analyses")
