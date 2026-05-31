from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.ticket import BlockingReason, FieldReport, ModerationTicket
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.infrastructure.database.models.ticket import (
    BlockingReasonModel,
    ModerationFieldReportModel,
    ModerationTicketModel,
)


class SQLAlchemyTicketRepository(AbstractTicketRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, ticket: ModerationTicket) -> None:
        model = ModerationTicketModel(
            id=ticket.id,
            product_id=ticket.product_id,
            seller_id=ticket.seller_id,
            category_id=ticket.category_id,
            kind=ticket.kind,
            status=ticket.status,
            queue_priority=ticket.queue_priority,
            json_before=ticket.json_before,
            json_after=ticket.json_after,
        )
        self._session.add(model)
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

        model.status = ticket.status
        model.decision_at = ticket.decision_at
        model.decision_comment = ticket.decision_comment
        model.blocking_reason_id = ticket.blocking_reason_id
        model.updated_at = ticket.updated_at
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
