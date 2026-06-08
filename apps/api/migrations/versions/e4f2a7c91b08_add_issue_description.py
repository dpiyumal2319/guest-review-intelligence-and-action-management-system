"""add_issue_description

Revision ID: e4f2a7c91b08
Revises: daa1b3c587f2
Create Date: 2026-06-08 13:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e4f2a7c91b08'
down_revision: str | None = 'daa1b3c587f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'detected_issues',
        sa.Column('description', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('detected_issues', 'description')
