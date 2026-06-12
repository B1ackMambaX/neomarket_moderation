"""claim queue indexes

Revision ID: a8142d0be721
Revises: 42c18eab09d7
Create Date: 2026-06-12 13:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8142d0be721"
down_revision: Union[str, None] = "42c18eab09d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_moderation_tickets_pending_queue",
        "moderation_tickets",
        ["queue_priority", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "uq_moderation_tickets_active_moderator",
        "moderation_tickets",
        ["assigned_moderator_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'IN_REVIEW' AND assigned_moderator_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_moderation_tickets_active_moderator",
        table_name="moderation_tickets",
        postgresql_where=sa.text(
            "status = 'IN_REVIEW' AND assigned_moderator_id IS NOT NULL"
        ),
    )
    op.drop_index(
        "ix_moderation_tickets_pending_queue",
        table_name="moderation_tickets",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
