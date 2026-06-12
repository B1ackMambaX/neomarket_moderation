from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.ticket import BlockingReason


class AbstractBlockingReasonRepository(ABC):
    @abstractmethod
    async def list(
        self,
        *,
        hard_block: bool | None,
        is_active: bool,
    ) -> list[BlockingReason]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, reason_id: UUID) -> BlockingReason | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_code(self, code: str) -> BlockingReason | None:
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        code: str,
        title: str,
        description: str | None,
        hard_block: bool,
    ) -> BlockingReason:
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        reason_id: UUID,
        changes: dict[str, object],
    ) -> BlockingReason | None:
        raise NotImplementedError

    @abstractmethod
    async def deactivate(self, reason_id: UUID) -> bool:
        raise NotImplementedError
