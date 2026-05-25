from datetime import datetime, timezone
from uuid import UUID

from app.domain.entities.ticket import TicketStatus
from app.domain.exceptions import (
    ConflictException,
    NotFoundException,
    PermissionDeniedException,
    UpstreamServiceException,
)
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.services.b2b_moderation_client import AbstractB2BModerationClient


class TicketService:
    def __init__(
        self,
        ticket_repository: AbstractTicketRepository,
        b2b_client: AbstractB2BModerationClient,
    ) -> None:
        self._tickets = ticket_repository
        self._b2b_client = b2b_client

    async def approve_ticket(
        self,
        *,
        ticket_id: UUID,
        moderator_id: UUID,
        comment: str | None,
    ):
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundException("Ticket not found")

        if ticket.status == TicketStatus.HARD_BLOCKED:
            raise ConflictException("Product is permanently blocked")
        if ticket.status != TicketStatus.IN_REVIEW:
            raise ConflictException("Product was edited during review")
        if ticket.assigned_moderator_id != moderator_id:
            raise PermissionDeniedException(
                "This moderation card is not assigned to you"
            )
        if not ticket.has_skus():
            raise ConflictException("Product has no SKUs, cannot approve")

        now = datetime.now(timezone.utc)
        previous_status = ticket.status
        ticket.status = TicketStatus.APPROVED
        ticket.decision_at = now
        ticket.decision_comment = comment
        ticket.updated_at = now

        try:
            await self._b2b_client.send_moderated_event(
                idempotency_key=ticket.id,
                product_id=ticket.product_id,
                moderator_id=moderator_id,
                moderator_comment=comment,
                occurred_at=now,
            )
        except Exception as exc:
            ticket.status = previous_status
            ticket.decision_at = None
            ticket.decision_comment = None
            ticket.updated_at = now
            raise UpstreamServiceException(
                f"B2B service unavailable: {exc}"
            ) from exc

        await self._tickets.clear_field_reports(ticket.id)
        await self._tickets.save(ticket)
        return ticket
