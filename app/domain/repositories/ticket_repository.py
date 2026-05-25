from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.ticket import ModerationTicket


class AbstractTicketRepository(ABC):
    @abstractmethod
    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, ticket: ModerationTicket) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear_field_reports(self, ticket_id: UUID) -> None:
        raise NotImplementedError
