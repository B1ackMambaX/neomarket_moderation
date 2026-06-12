"""add sku_id to moderation_field_reports

Revision ID: c2d3e4f5a6b7
Revises: f6b7c8d9e0a1
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "f6b7c8d9e0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "moderation_field_reports",
        sa.Column("sku_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("moderation_field_reports", "sku_id")
