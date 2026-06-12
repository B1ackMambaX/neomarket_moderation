from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.ticket import TicketKind, TicketStatus
from app.infrastructure.database.models.base import Base, TimestampMixin


class ModerationTicketModel(Base, TimestampMixin):
    __tablename__ = "moderation_tickets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(index=True, unique=True)
    seller_id: Mapped[UUID] = mapped_column(index=True)
    category_id: Mapped[UUID | None] = mapped_column(nullable=True)
    kind: Mapped[TicketKind] = mapped_column(Enum(TicketKind), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), nullable=False)
    queue_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    assigned_moderator_id: Mapped[UUID | None] = mapped_column(nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(String(2000))
    blocking_reason_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("blocking_reasons.id", ondelete="RESTRICT"),
        nullable=True,
    )
    json_before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_after: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ProcessedProductEventModel(Base):
    __tablename__ = "processed_product_events"

    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ModerationFieldReportModel(Base, TimestampMixin):
    __tablename__ = "moderation_field_reports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    field_path: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")


class BlockingReasonModel(Base, TimestampMixin):
    __tablename__ = "blocking_reasons"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    hard_block: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
