"""add calendar auto dispatch

Revision ID: b7e21c5d4a90
Revises: a2f4d3b9c801
Create Date: 2026-05-05 15:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e21c5d4a90"
down_revision: Union[str, Sequence[str], None] = "a2f4d3b9c801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "google_connection",
        sa.Column("auto_dispatch_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "calendar_dispatches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("google_event_id", sa.String(), nullable=False),
        sa.Column("meeting_id", sa.String(), nullable=True),
        sa.Column("meeting_url", sa.String(), nullable=False),
        sa.Column("event_title", sa.String(), nullable=True),
        sa.Column("event_start", sa.DateTime(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_calendar_dispatches_google_event_id"),
        "calendar_dispatches",
        ["google_event_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_calendar_dispatches_meeting_id"),
        "calendar_dispatches",
        ["meeting_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_calendar_dispatches_meeting_id"), table_name="calendar_dispatches")
    op.drop_index(op.f("ix_calendar_dispatches_google_event_id"), table_name="calendar_dispatches")
    op.drop_table("calendar_dispatches")
    op.drop_column("google_connection", "auto_dispatch_enabled")
