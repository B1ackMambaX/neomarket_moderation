from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Integer, String
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
    json_before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_after: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ModerationFieldReportModel(Base, TimestampMixin):
    __tablename__ = "moderation_field_reports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    field_path: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")
