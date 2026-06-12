from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities.ticket import (
    FieldReport,
    ModerationTicket,
    TicketKind,
    TicketStatus,
)


class ApproveTicketRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class FieldReportRequest(BaseModel):
    field_path: str = Field(max_length=255)
    message: str = Field(max_length=2000)
    severity: str = "ERROR"

    def to_entity(self) -> FieldReport:
        return FieldReport(
            field_path=self.field_path,
            message=self.message,
            severity=self.severity,
        )


class BlockTicketRequest(BaseModel):
    blocking_reason_ids: list[UUID] = Field(min_length=1)
    comment: str | None = Field(default=None, max_length=2000)
    field_reports: list[FieldReportRequest] = Field(default_factory=list)


class IncomingB2BEvent(BaseModel):
    event_type: Literal["PRODUCT_CREATED", "PRODUCT_EDITED", "PRODUCT_DELETED"]
    idempotency_key: UUID
    occurred_at: datetime
    payload: dict


class ProductEventRequest(BaseModel):
    idempotency_key: UUID
    product_id: UUID
    seller_id: UUID
    event: Literal["CREATED", "EDITED", "DELETED"]
    date: datetime


class TicketResponse(BaseModel):
    id: UUID
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    kind: TicketKind
    status: TicketStatus
    queue_priority: int = Field(ge=1, le=4)
    assigned_moderator_id: UUID | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    decision_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, ticket: ModerationTicket) -> "TicketResponse":
        if ticket.created_at is None:
            raise ValueError("Ticket created_at is required by OpenAPI response")
        return cls(
            id=ticket.id,
            product_id=ticket.product_id,
            seller_id=ticket.seller_id,
            category_id=ticket.category_id,
            kind=ticket.kind,
            status=ticket.status,
            queue_priority=ticket.queue_priority,
            assigned_moderator_id=ticket.assigned_moderator_id,
            claimed_at=ticket.claimed_at,
            claim_expires_at=ticket.claim_expires_at,
            decision_at=ticket.decision_at,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )
