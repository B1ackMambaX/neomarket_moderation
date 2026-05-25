from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.entities.ticket import FieldReport, ModerationTicket, TicketKind, TicketStatus
from app.domain.exceptions import (
    ConflictException,
    NotFoundException,
    PermissionDeniedException,
    UpstreamServiceException,
    ValidationException,
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

        if ticket.is_terminal():
            raise PermissionDeniedException("Product is permanently blocked")
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

    async def block_ticket(
        self,
        *,
        ticket_id: UUID,
        moderator_id: UUID,
        blocking_reason_ids: list[UUID],
        comment: str | None,
        field_reports: list[FieldReport],
    ):
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundException("Ticket not found")

        if ticket.is_terminal():
            raise PermissionDeniedException("Product is permanently blocked")
        if ticket.status != TicketStatus.IN_REVIEW:
            raise ConflictException("Product was edited during review")
        if ticket.assigned_moderator_id != moderator_id:
            raise PermissionDeniedException(
                "This moderation card is not assigned to you"
            )

        reasons = await self._tickets.get_blocking_reasons(blocking_reason_ids)
        if len(reasons) != len(set(blocking_reason_ids)):
            raise ValidationException("Unknown or inactive blocking reason")

        selected_reason = next(
            (reason for reason in reasons if reason.hard_block),
            None,
        )
        if selected_reason is None:
            selected_reason = reasons[0]

        now = datetime.now(timezone.utc)
        previous_status = ticket.status
        previous_decision_at = ticket.decision_at
        previous_decision_comment = ticket.decision_comment
        previous_blocking_reason_id = ticket.blocking_reason_id
        previous_updated_at = ticket.updated_at

        ticket.status = (
            TicketStatus.HARD_BLOCKED
            if selected_reason.hard_block
            else TicketStatus.BLOCKED
        )
        ticket.decision_at = now
        ticket.decision_comment = comment
        ticket.blocking_reason_id = selected_reason.id
        ticket.updated_at = now

        event_reports = [
            {
                "field_name": report.field_path,
                "sku_id": None,
                "comment": report.message,
            }
            for report in field_reports
        ]

        try:
            await self._b2b_client.send_blocked_event(
                idempotency_key=ticket.id,
                product_id=ticket.product_id,
                moderator_id=moderator_id,
                moderator_comment=comment,
                blocking_reason_id=selected_reason.id,
                hard_block=selected_reason.hard_block,
                field_reports=event_reports,
                occurred_at=now,
            )
        except Exception as exc:
            ticket.status = previous_status
            ticket.decision_at = previous_decision_at
            ticket.decision_comment = previous_decision_comment
            ticket.blocking_reason_id = previous_blocking_reason_id
            ticket.updated_at = previous_updated_at
            raise UpstreamServiceException(
                f"B2B service unavailable: {exc}"
            ) from exc

        await self._tickets.clear_field_reports(ticket.id)
        await self._tickets.save_field_reports(ticket.id, field_reports)
        await self._tickets.save(ticket)
        return ticket

    async def apply_b2b_event(
        self,
        *,
        event_type: str,
        payload: dict,
    ) -> None:
        product_id = UUID(payload["product_id"])

        if event_type == "PRODUCT_CREATED":
            now = datetime.now(timezone.utc)
            ticket = ModerationTicket(
                id=uuid4(),
                product_id=product_id,
                seller_id=UUID(payload["seller_id"]),
                category_id=UUID(payload["category_id"]) if payload.get("category_id") else None,
                kind=TicketKind.CREATE,
                status=TicketStatus.PENDING,
                queue_priority=payload.get("queue_priority", 3),
                json_after=payload["json_after"],
                created_at=now,
                updated_at=now,
            )
            await self._tickets.create(ticket)
            return

        ticket = await self._tickets.get_by_product_id(product_id)

        if event_type == "PRODUCT_DELETED":
            await self._tickets.delete_by_product_id(product_id)
            return

        if (
            event_type == "PRODUCT_EDITED"
            and ticket is not None
            and ticket.is_terminal()
        ):
            return

        if event_type == "PRODUCT_EDITED" and ticket is not None:
            ticket.status = TicketStatus.PENDING
            ticket.kind = TicketKind.EDIT
            ticket.json_before = payload.get("json_before")
            ticket.json_after = payload["json_after"]
            ticket.category_id = payload.get("category_id")
            ticket.queue_priority = payload.get("queue_priority", ticket.queue_priority)
            ticket.assigned_moderator_id = None
            ticket.claimed_at = None
            ticket.claim_expires_at = None
            ticket.updated_at = datetime.now(timezone.utc)
            await self._tickets.save(ticket)
