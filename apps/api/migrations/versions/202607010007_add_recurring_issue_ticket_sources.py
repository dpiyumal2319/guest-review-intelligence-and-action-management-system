"""add recurring issue ticket source metadata

Revision ID: 202607010007
Revises: 202607010006
Create Date: 2026-07-01 00:07:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607010007"
down_revision: str | None = "202607010006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("action_tickets") as batch_op:
        batch_op.alter_column("review_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("source_group_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("source_group_key", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("source_group_label", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("source_category_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("source_cluster_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("source_review_ids", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_action_tickets_source_category_code_issue_categories",
            "issue_categories",
            ["source_category_code"],
            ["code"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_action_tickets_source_group",
            ["source_group_type", "source_group_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("action_tickets") as batch_op:
        batch_op.drop_index("ix_action_tickets_source_group")
        batch_op.drop_constraint("fk_action_tickets_source_category_code_issue_categories", type_="foreignkey")
        batch_op.drop_column("source_review_ids")
        batch_op.drop_column("source_cluster_id")
        batch_op.drop_column("source_category_code")
        batch_op.drop_column("source_group_label")
        batch_op.drop_column("source_group_key")
        batch_op.drop_column("source_group_type")
        batch_op.alter_column("review_id", existing_type=sa.Integer(), nullable=False)
