from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.ticket import BlockingReason, FieldReport, ModerationTicket
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.infrastructure.database.models.ticket import (
    BlockingReasonModel,
    ModerationFieldReportModel,
    ModerationTicketModel,
    ProcessedProductEventModel,
)


class SQLAlchemyTicketRepository(AbstractTicketRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, ticket: ModerationTicket) -> None:
        self._session.add(self._to_model(ticket))
        await self._session.commit()

    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        result = await self._session.execute(
            select(ModerationTicketModel).where(ModerationTicketModel.id == ticket_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def get_by_product_id(self, product_id: UUID) -> ModerationTicket | None:
        result = await self._session.execute(
            select(ModerationTicketModel).where(
                ModerationTicketModel.product_id == product_id
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def get_blocking_reasons(
        self, reason_ids: list[UUID]
    ) -> list[BlockingReason]:
        result = await self._session.execute(
            select(BlockingReasonModel).where(
                BlockingReasonModel.id.in_(reason_ids),
                BlockingReasonModel.is_active.is_(True),
            )
        )
        return [
            BlockingReason(id=model.id, title=model.title, hard_block=model.hard_block)
            for model in result.scalars()
        ]

    async def save(self, ticket: ModerationTicket) -> None:
        model = await self._session.get(ModerationTicketModel, ticket.id)
        if model is None:
            raise RuntimeError("Cannot save missing moderation ticket")

        self._update_model(model, ticket)
        await self._session.commit()

    async def save_field_reports(
        self, ticket_id: UUID, field_reports: list[FieldReport]
    ) -> None:
        self._session.add_all(
            [
                ModerationFieldReportModel(
                    ticket_id=ticket_id,
                    field_path=report.field_path,
                    message=report.message,
                    severity=report.severity,
                )
                for report in field_reports
            ]
        )
        await self._session.commit()

    async def clear_field_reports(self, ticket_id: UUID) -> None:
        await self._session.execute(
            delete(ModerationFieldReportModel).where(
                ModerationFieldReportModel.ticket_id == ticket_id
            )
        )
        await self._session.commit()

    async def delete_by_product_id(self, product_id: UUID) -> None:
        await self._session.execute(
            delete(ModerationTicketModel).where(
                ModerationTicketModel.product_id == product_id
            )
        )
        await self._session.commit()

    async def is_event_processed(self, idempotency_key: UUID) -> bool:
        result = await self._session.execute(
            select(ProcessedProductEventModel.idempotency_key).where(
                ProcessedProductEventModel.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none() is not None

    async def mark_event_processed(
        self,
        idempotency_key: UUID,
        product_id: UUID,
        occurred_at: datetime,
    ) -> bool:
        if not await self._try_add_event(idempotency_key, product_id, occurred_at):
            await self._session.commit()
            return False
        await self._session.commit()
        return True

    async def create_from_event(
        self,
        ticket: ModerationTicket,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        if not await self._try_add_event(
            idempotency_key, ticket.product_id, occurred_at
        ):
            await self._session.commit()
            return False
        self._session.add(self._to_model(ticket))
        await self._session.commit()
        return True

    async def save_from_event(
        self,
        ticket: ModerationTicket,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        if not await self._try_add_event(
            idempotency_key, ticket.product_id, occurred_at
        ):
            await self._session.commit()
            return False

        model = await self._session.get(ModerationTicketModel, ticket.id)
        if model is None:
            raise RuntimeError("Cannot save missing moderation ticket")
        self._update_model(model, ticket)
        await self._session.execute(
            delete(ModerationFieldReportModel).where(
                ModerationFieldReportModel.ticket_id == ticket.id
            )
        )
        await self._session.commit()
        return True

    async def delete_from_event(
        self,
        product_id: UUID,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        if not await self._try_add_event(idempotency_key, product_id, occurred_at):
            await self._session.commit()
            return False
        await self._session.execute(
            delete(ModerationTicketModel).where(
                ModerationTicketModel.product_id == product_id
            )
        )
        await self._session.commit()
        return True

    async def _try_add_event(
        self,
        idempotency_key: UUID,
        product_id: UUID,
        occurred_at: datetime,
    ) -> bool:
        statement = (
            insert(ProcessedProductEventModel)
            .values(
                idempotency_key=idempotency_key,
                product_id=product_id,
                occurred_at=occurred_at,
                processed_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(ProcessedProductEventModel.idempotency_key)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _to_model(ticket: ModerationTicket) -> ModerationTicketModel:
        return ModerationTicketModel(
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
            decision_comment=ticket.decision_comment,
            blocking_reason_id=ticket.blocking_reason_id,
            json_before=ticket.json_before,
            json_after=ticket.json_after,
        )

    @staticmethod
    def _update_model(
        model: ModerationTicketModel,
        ticket: ModerationTicket,
    ) -> None:
        model.seller_id = ticket.seller_id
        model.category_id = ticket.category_id
        model.kind = ticket.kind
        model.status = ticket.status
        model.queue_priority = ticket.queue_priority
        model.assigned_moderator_id = ticket.assigned_moderator_id
        model.claimed_at = ticket.claimed_at
        model.claim_expires_at = ticket.claim_expires_at
        model.decision_at = ticket.decision_at
        model.decision_comment = ticket.decision_comment
        model.blocking_reason_id = ticket.blocking_reason_id
        model.json_before = ticket.json_before
        model.json_after = ticket.json_after
        model.updated_at = ticket.updated_at

    @staticmethod
    def _to_entity(model: ModerationTicketModel) -> ModerationTicket:
        return ModerationTicket(
            id=model.id,
            product_id=model.product_id,
            seller_id=model.seller_id,
            category_id=model.category_id,
            kind=model.kind,
            status=model.status,
            queue_priority=model.queue_priority,
            assigned_moderator_id=model.assigned_moderator_id,
            claimed_at=model.claimed_at,
            claim_expires_at=model.claim_expires_at,
            decision_at=model.decision_at,
            decision_comment=model.decision_comment,
            blocking_reason_id=model.blocking_reason_id,
            json_before=model.json_before,
            json_after=model.json_after,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
