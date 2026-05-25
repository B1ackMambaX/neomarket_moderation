"""moderation_tickets

Revision ID: d533262995c7
Revises:
Create Date: 2026-05-24 22:33:50.214203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd533262995c7'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'moderation_tickets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('seller_id', sa.Uuid(), nullable=False),
        sa.Column('category_id', sa.Uuid(), nullable=True),
        sa.Column('kind', sa.Enum('CREATE', 'EDIT', name='ticketkind'), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'IN_REVIEW', 'APPROVED', 'BLOCKED', 'HARD_BLOCKED', name='ticketstatus'), nullable=False),
        sa.Column('queue_priority', sa.Integer(), nullable=False),
        sa.Column('assigned_moderator_id', sa.Uuid(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claim_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_comment', sa.String(length=2000), nullable=True),
        sa.Column('json_before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('json_after', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_moderation_tickets_product_id'), 'moderation_tickets', ['product_id'], unique=True)
    op.create_index(op.f('ix_moderation_tickets_seller_id'), 'moderation_tickets', ['seller_id'], unique=False)

    op.create_table(
        'moderation_field_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('ticket_id', sa.Uuid(), nullable=False),
        sa.Column('field_path', sa.String(length=255), nullable=False),
        sa.Column('message', sa.String(length=2000), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['moderation_tickets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_moderation_field_reports_ticket_id'), 'moderation_field_reports', ['ticket_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_moderation_field_reports_ticket_id'), table_name='moderation_field_reports')
    op.drop_table('moderation_field_reports')
    op.drop_index(op.f('ix_moderation_tickets_seller_id'), table_name='moderation_tickets')
    op.drop_index(op.f('ix_moderation_tickets_product_id'), table_name='moderation_tickets')
    op.drop_table('moderation_tickets')
    op.execute('DROP TYPE IF EXISTS ticketstatus')
    op.execute('DROP TYPE IF EXISTS ticketkind')
