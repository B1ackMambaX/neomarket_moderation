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
        idempotency_key: UUID,
        occurred_at: datetime,
        product_id: UUID | str,
        seller_id: UUID | str | None,
        payload: dict | None = None,
    ) -> None:
        product_id = UUID(str(product_id))
        if await self._tickets.is_event_processed(idempotency_key):
            return

        ticket = await self._tickets.get_by_product_id(product_id)

        if event_type == "CREATED":
            if ticket is not None and ticket.is_terminal():
                await self._tickets.mark_event_processed(
                    idempotency_key, product_id, occurred_at
                )
                return
            if ticket is not None:
                raise ValidationException("Product moderation ticket already exists")
            if seller_id is None:
                raise ValidationException("seller_id is required for CREATED")

            snapshot = await self._product_snapshot(product_id, payload)
            now = datetime.now(timezone.utc)
            ticket = ModerationTicket(
                id=uuid4(),
                product_id=product_id,
                seller_id=UUID(str(seller_id)),
                category_id=self._optional_uuid(snapshot.get("category_id")),
                kind=TicketKind.CREATE,
                status=TicketStatus.PENDING,
                queue_priority=payload.get("queue_priority", 1) if payload else 1,
                json_after=snapshot,
                created_at=now,
                updated_at=now,
            )
            await self._tickets.create_from_event(ticket, idempotency_key, occurred_at)
            return

        if event_type == "DELETED":
            await self._tickets.delete_from_event(
                product_id, idempotency_key, occurred_at
            )
            return

        if event_type != "EDITED":
            raise ValidationException(f"Unknown product event: {event_type}")
        if ticket is None:
            raise ValidationException("Product moderation ticket not found")
        if ticket.is_terminal():
            await self._tickets.mark_event_processed(
                idempotency_key, product_id, occurred_at
            )
            return

        old_status = ticket.status
        snapshot = await self._product_snapshot(product_id, payload)
        ticket.status = TicketStatus.PENDING
        ticket.kind = TicketKind.EDIT
        ticket.json_before = ticket.json_after
        ticket.json_after = snapshot
        ticket.category_id = self._optional_uuid(snapshot.get("category_id"))
        ticket.queue_priority = self._edited_priority(
            old_status, snapshot, ticket.queue_priority
        )
        ticket.assigned_moderator_id = None
        ticket.claimed_at = None
        ticket.claim_expires_at = None
        ticket.decision_at = None
        ticket.decision_comment = None
        ticket.blocking_reason_id = None
        ticket.updated_at = datetime.now(timezone.utc)
        await self._tickets.save_from_event(ticket, idempotency_key, occurred_at)

    async def _product_snapshot(self, product_id: UUID, payload: dict | None) -> dict:
        if payload is not None and "json_after" in payload:
            snapshot = dict(payload["json_after"])
            if "category_id" not in snapshot and payload.get("category_id"):
                snapshot["category_id"] = payload["category_id"]
            return snapshot
        return await self._b2b_client.get_product(product_id)

    @staticmethod
    def _optional_uuid(value: object) -> UUID | None:
        return UUID(str(value)) if value else None

    @staticmethod
    def _edited_priority(
        old_status: TicketStatus,
        snapshot: dict,
        current_priority: int,
    ) -> int:
        if old_status == TicketStatus.BLOCKED:
            return 2
        if old_status == TicketStatus.APPROVED:
            quantity = snapshot.get("total_active_quantity")
            if quantity is None:
                quantity = sum(
                    sku.get("active_quantity", 0)
                    for sku in snapshot.get("skus", [])
                    if isinstance(sku, dict)
                )
            return 3 if quantity > 0 else 4
        return current_priority
