"""create action tickets and ticket events

Revision ID: 202607010006
Revises: 202607010005
Create Date: 2026-07-01 00:06:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607010006"
down_revision: str | None = "202607010005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_tickets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "review_id",
            sa.Integer(),
            sa.ForeignKey("normalized_reviews.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "department_code",
            sa.String(length=64),
            sa.ForeignKey("departments.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("assignee_name", sa.String(length=120), nullable=True),
        sa.Column("assignee_email", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_action_tickets_review_id", "action_tickets", ["review_id"])
    op.create_index("ix_action_tickets_department_status", "action_tickets", ["department_code", "status"])

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("action_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.String(length=255), nullable=True),
        sa.Column("new_value", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_events_ticket_id", table_name="ticket_events")
    op.drop_table("ticket_events")
    op.drop_index("ix_action_tickets_department_status", table_name="action_tickets")
    op.drop_index("ix_action_tickets_review_id", table_name="action_tickets")
    op.drop_table("action_tickets")
