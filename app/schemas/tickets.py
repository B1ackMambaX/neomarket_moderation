from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities.ticket import ModerationTicket, TicketKind, TicketStatus


class ApproveTicketRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


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
