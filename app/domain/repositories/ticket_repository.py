from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.entities.ticket import BlockingReason, FieldReport, ModerationTicket


@dataclass(frozen=True, slots=True)
class ClaimNextResult:
    ticket: ModerationTicket | None = None
    moderator_already_has_ticket: bool = False


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
    async def claim_next(
        self,
        *,
        moderator_id: UUID,
        queue_priority: int | None,
        category_ids: list[UUID] | None,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> ClaimNextResult:
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

    async def is_event_processed(self, idempotency_key: UUID) -> bool:
        raise NotImplementedError

    async def mark_event_processed(
        self,
        idempotency_key: UUID,
        product_id: UUID,
        occurred_at: datetime,
    ) -> bool:
        raise NotImplementedError

    async def create_from_event(
        self,
        ticket: ModerationTicket,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        raise NotImplementedError

    async def save_from_event(
        self,
        ticket: ModerationTicket,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        raise NotImplementedError

    async def delete_from_event(
        self,
        product_id: UUID,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        raise NotImplementedError
