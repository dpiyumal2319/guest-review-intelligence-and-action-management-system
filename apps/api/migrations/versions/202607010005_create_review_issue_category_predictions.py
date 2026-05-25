"""create review issue category predictions

Revision ID: 202607010005
Revises: 202607010004
Create Date: 2026-07-01 00:05:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607010005"
down_revision: str | None = "202607010004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_issue_category_predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("review_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_code",
            sa.String(length=64),
            sa.ForeignKey("issue_categories.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "department_code",
            sa.String(length=64),
            sa.ForeignKey("departments.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_review_issue_category_predictions_analysis_rank",
        "review_issue_category_predictions",
        ["analysis_id", "rank"],
        unique=True,
    )
    op.create_index(
        "ix_review_issue_category_predictions_category",
        "review_issue_category_predictions",
        ["category_code", "is_primary"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_issue_category_predictions_category", table_name="review_issue_category_predictions")
    op.drop_index("ix_review_issue_category_predictions_analysis_rank", table_name="review_issue_category_predictions")
    op.drop_table("review_issue_category_predictions")
