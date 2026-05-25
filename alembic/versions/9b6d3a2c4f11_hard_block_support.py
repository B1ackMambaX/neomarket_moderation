"""hard block support

Revision ID: 9b6d3a2c4f11
Revises: d533262995c7
Create Date: 2026-05-24 23:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9b6d3a2c4f11"
down_revision: Union[str, None] = "d533262995c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "moderation_tickets",
        sa.Column("blocking_reason_id", sa.Uuid(), nullable=True),
    )
    op.create_table(
        "blocking_reasons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("hard_block", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_blocking_reasons_code"),
        "blocking_reasons",
        ["code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_blocking_reasons_code"), table_name="blocking_reasons")
    op.drop_table("blocking_reasons")
    op.drop_column("moderation_tickets", "blocking_reason_id")
