"""create reference configuration tables

Revision ID: 202607010001
Revises:
Create Date: 2026-07-01 00:01:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607010001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_sources",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified_channel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("connector_key", sa.String(length=120), nullable=True),
        sa.Column("sample_import_path", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.CheckConstraint(
            "source_type in ('verified_review', 'social_listening', 'seed_dataset', 'apify_dataset_import')",
            name="ck_review_sources_source_type",
        ),
    )
    op.create_table(
        "departments",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("service_level_hours", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_table(
        "issue_categories",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_positive_signal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_table(
        "category_department_mappings",
        sa.Column(
            "category_code",
            sa.String(length=64),
            sa.ForeignKey("issue_categories.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "department_code",
            sa.String(length=64),
            sa.ForeignKey("departments.code", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("routing_notes", sa.Text(), nullable=False),
    )
    op.create_table(
        "reputation_risk_thresholds",
        sa.Column(
            "category_code",
            sa.String(length=64),
            sa.ForeignKey("issue_categories.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("low_rating_max", sa.Numeric(3, 2), nullable=False),
        sa.Column("negative_sentiment_max", sa.Numeric(4, 3), nullable=False),
        sa.Column("urgent_confidence_min", sa.Numeric(4, 3), nullable=False),
        sa.Column("recurring_count_7d_min", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "demo_roles",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("department_scope", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_table("demo_roles")
    op.drop_table("reputation_risk_thresholds")
    op.drop_table("category_department_mappings")
    op.drop_table("issue_categories")
    op.drop_table("departments")
    op.drop_table("review_sources")
