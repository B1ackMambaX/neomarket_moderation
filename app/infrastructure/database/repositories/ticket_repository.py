from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.ticket import ModerationTicket
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.infrastructure.database.models.ticket import (
    ModerationFieldReportModel,
    ModerationTicketModel,
)


class SQLAlchemyTicketRepository(AbstractTicketRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        result = await self._session.execute(
            select(ModerationTicketModel).where(ModerationTicketModel.id == ticket_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def save(self, ticket: ModerationTicket) -> None:
        model = await self._session.get(ModerationTicketModel, ticket.id)
        if model is None:
            raise RuntimeError("Cannot save missing moderation ticket")

        model.status = ticket.status
        model.decision_at = ticket.decision_at
        model.decision_comment = ticket.decision_comment
        model.updated_at = ticket.updated_at
        await self._session.commit()

    async def clear_field_reports(self, ticket_id: UUID) -> None:
        await self._session.execute(
            delete(ModerationFieldReportModel).where(
                ModerationFieldReportModel.ticket_id == ticket_id
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
            json_before=model.json_before,
            json_after=model.json_after,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
