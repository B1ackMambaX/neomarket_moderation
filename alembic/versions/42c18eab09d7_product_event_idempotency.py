"""product event idempotency

Revision ID: 42c18eab09d7
Revises: 9b6d3a2c4f11
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "42c18eab09d7"
down_revision: Union[str, None] = "9b6d3a2c4f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processed_product_events",
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )
    op.create_index(
        op.f("ix_processed_product_events_product_id"),
        "processed_product_events",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_processed_product_events_product_id"),
        table_name="processed_product_events",
    )
    op.drop_table("processed_product_events")
