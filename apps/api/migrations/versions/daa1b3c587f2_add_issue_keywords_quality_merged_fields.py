"""add_issue_keywords_quality_merged_fields

Revision ID: daa1b3c587f2
Revises: cc291a0f3582
Create Date: 2026-06-08 12:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'daa1b3c587f2'
down_revision: str | None = 'cc291a0f3582'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'detected_issues',
        sa.Column('keywords', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.add_column(
        'detected_issues',
        sa.Column('title_quality_score', sa.Float(), nullable=True),
    )
    op.add_column(
        'detected_issues',
        sa.Column('merged_from_id', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('detected_issues', 'merged_from_id')
    op.drop_column('detected_issues', 'title_quality_score')
    op.drop_column('detected_issues', 'keywords')
