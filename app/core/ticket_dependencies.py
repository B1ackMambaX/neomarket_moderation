from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.infrastructure.database.repositories.ticket_repository import (
    SQLAlchemyTicketRepository,
)
from app.services.b2b_moderation_client import (
    AbstractB2BModerationClient,
    HttpB2BModerationClient,
)
from app.services.ticket_service import TicketService


async def get_ticket_repository(
    db: AsyncSession = Depends(get_db),
) -> AbstractTicketRepository:
    return SQLAlchemyTicketRepository(db)


async def get_b2b_moderation_client() -> AbstractB2BModerationClient:
    return HttpB2BModerationClient()


async def get_ticket_service(
    ticket_repository: AbstractTicketRepository = Depends(get_ticket_repository),
    b2b_client: AbstractB2BModerationClient = Depends(get_b2b_moderation_client),
) -> TicketService:
    return TicketService(ticket_repository, b2b_client)
