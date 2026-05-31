from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.ticket import BlockingReason, FieldReport, ModerationTicket


class AbstractTicketRepository(ABC):
    @abstractmethod
    async def create(self, ticket: ModerationTicket) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_product_id(self, product_id: UUID) -> ModerationTicket | None:
        raise NotImplementedError

    @abstractmethod
    async def get_blocking_reasons(
        self, reason_ids: list[UUID]
    ) -> list[BlockingReason]:
        raise NotImplementedError

    @abstractmethod
    async def save(self, ticket: ModerationTicket) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save_field_reports(
        self, ticket_id: UUID, field_reports: list[FieldReport]
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear_field_reports(self, ticket_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_product_id(self, product_id: UUID) -> None:
        raise NotImplementedError
