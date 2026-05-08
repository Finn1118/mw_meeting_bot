"""add platform ownership fields

Revision ID: 5c4e7f8a9b12
Revises: b057596f7ee2
Create Date: 2026-05-05 14:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5c4e7f8a9b12"
down_revision: Union[str, Sequence[str], None] = "b057596f7ee2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("meetings", sa.Column("org_id", sa.String(), nullable=True))
    op.add_column("meetings", sa.Column("created_by_uid", sa.String(), nullable=True))
    op.add_column("meetings", sa.Column("platform_conversation_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_meetings_org_id"), "meetings", ["org_id"], unique=False)
    op.create_index(op.f("ix_meetings_created_by_uid"), "meetings", ["created_by_uid"], unique=False)
    op.create_index(
        op.f("ix_meetings_platform_conversation_id"),
        "meetings",
        ["platform_conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_meetings_platform_conversation_id"), table_name="meetings")
    op.drop_index(op.f("ix_meetings_created_by_uid"), table_name="meetings")
    op.drop_index(op.f("ix_meetings_org_id"), table_name="meetings")
    op.drop_column("meetings", "platform_conversation_id")
    op.drop_column("meetings", "created_by_uid")
    op.drop_column("meetings", "org_id")
