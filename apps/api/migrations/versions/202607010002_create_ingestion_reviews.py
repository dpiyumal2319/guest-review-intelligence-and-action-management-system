"""create ingestion and review tables

Revision ID: 202607010002
Revises: 202607010001
Create Date: 2026-07-01 00:02:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607010002"
down_revision: str | None = "202607010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("connector_key", sa.String(length=120), nullable=False),
        sa.Column(
            "source_code",
            sa.String(length=64),
            sa.ForeignKey("review_sources.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_table(
        "raw_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_code",
            sa.String(length=64),
            sa.ForeignKey("review_sources.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_review_id", sa.String(length=120), nullable=False),
        sa.Column(
            "ingestion_run_id",
            sa.Integer(),
            sa.ForeignKey("ingestion_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_code", "external_review_id", name="uq_raw_reviews_source_external_id"),
    )
    op.create_table(
        "normalized_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "raw_review_id",
            sa.Integer(),
            sa.ForeignKey("raw_reviews.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_code",
            sa.String(length=64),
            sa.ForeignKey("review_sources.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_review_id", sa.String(length=120), nullable=False),
        sa.Column("reviewer_name", sa.String(length=120), nullable=True),
        sa.Column("review_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sentiment_label", sa.String(length=32), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "issue_category_code",
            sa.String(length=64),
            sa.ForeignKey("issue_categories.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reputation_risk", sa.String(length=32), nullable=False),
        sa.Column(
            "department_code",
            sa.String(length=64),
            sa.ForeignKey("departments.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action_status", sa.String(length=32), nullable=False),
        sa.Column("normalized_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_code", "external_review_id", name="uq_normalized_reviews_source_external_id"),
    )


def downgrade() -> None:
    op.drop_table("normalized_reviews")
    op.drop_table("raw_reviews")
    op.drop_table("ingestion_runs")
