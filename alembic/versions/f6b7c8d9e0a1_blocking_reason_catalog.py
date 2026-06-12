"""blocking reason catalog

Revision ID: f6b7c8d9e0a1
Revises: a8142d0be721
Create Date: 2026-06-12 17:00:00.000000

"""
from typing import Sequence, Union
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision: str = "f6b7c8d9e0a1"
down_revision: Union[str, None] = "a8142d0be721"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REASONS = [
    (
        "a7b8c9d0-1234-5678-ef01-890123456789",
        "DESCRIPTION_MISMATCH",
        "Описание не соответствует товару",
        False,
    ),
    (
        "b8c9d0e1-2345-6789-f012-901234567890",
        "IMAGE_MISMATCH",
        "Изображение не соответствует товару",
        False,
    ),
    (
        "c9d0e1f2-3456-7890-0123-012345678901",
        "INVALID_CATEGORY",
        "Некорректная категория товара",
        False,
    ),
    (
        "d0e1f2a3-4567-8901-1234-123456789012",
        "INSUFFICIENT_INFORMATION",
        "Недостаточно информации о товаре",
        False,
    ),
    (
        "e1f2a3b4-5678-9012-2345-234567890123",
        "OFFENSIVE_MATERIALS",
        "Нецензурные или оскорбительные материалы",
        False,
    ),
    (
        "f2a3b4c5-6789-0123-3456-345678901234",
        "DUPLICATE_PRODUCT",
        "Дублирование существующего товара",
        False,
    ),
    (
        "a3b4c5d6-7890-1234-4567-456789012345",
        "INVALID_PRICE",
        "Некорректная цена",
        False,
    ),
    (
        "b4c5d6e7-8901-2345-5678-567890123456",
        "COUNTERFEIT_PRODUCT",
        "Контрафактный товар",
        True,
    ),
    (
        "c5d6e7f8-9012-3456-6789-678901234567",
        "FORBIDDEN_GOODS",
        "Товар запрещён к продаже на территории РФ",
        True,
    ),
    (
        "d6e7f8a9-0123-4567-7890-789012345678",
        "COPYRIGHT_VIOLATION",
        "Товар нарушает авторские права",
        True,
    ),
]


def upgrade() -> None:
    reasons = sa.table(
        "blocking_reasons",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.String()),
        sa.column("hard_block", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
    )
    op.execute(
        insert(reasons)
        .values(
            [
                {
                    "id": UUID(reason_id),
                    "code": code,
                    "title": title,
                    "description": None,
                    "hard_block": hard_block,
                    "is_active": True,
                }
                for reason_id, code, title, hard_block in REASONS
            ]
        )
        .on_conflict_do_nothing()
    )
    op.create_foreign_key(
        "fk_moderation_tickets_blocking_reason_id",
        "moderation_tickets",
        "blocking_reasons",
        ["blocking_reason_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    ids = ", ".join(f"'{reason[0]}'" for reason in REASONS)
    op.execute(
        sa.text(
            f"DELETE FROM blocking_reasons "
            f"WHERE id::text IN ({ids}) AND NOT EXISTS ("
            f"SELECT 1 FROM moderation_tickets "
            f"WHERE moderation_tickets.blocking_reason_id = blocking_reasons.id"
            f")"
        )
    )
    op.drop_constraint(
        "fk_moderation_tickets_blocking_reason_id",
        "moderation_tickets",
        type_="foreignkey",
    )
