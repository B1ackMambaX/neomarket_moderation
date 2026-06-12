from uuid import UUID

from app.domain.entities.ticket import BlockingReason
from app.domain.exceptions import ConflictException, NotFoundException
from app.domain.repositories.blocking_reason_repository import (
    AbstractBlockingReasonRepository,
)


class BlockingReasonService:
    def __init__(self, repository: AbstractBlockingReasonRepository) -> None:
        self._repository = repository

    async def list_reasons(
        self,
        *,
        hard_block: bool | None,
        is_active: bool,
    ) -> list[BlockingReason]:
        return await self._repository.list(
            hard_block=hard_block,
            is_active=is_active,
        )

    async def create_reason(
        self,
        *,
        code: str,
        title: str,
        description: str | None,
        hard_block: bool,
    ) -> BlockingReason:
        if await self._repository.get_by_code(code) is not None:
            raise ConflictException("Blocking reason code already exists")
        return await self._repository.create(
            code=code,
            title=title,
            description=description,
            hard_block=hard_block,
        )

    async def update_reason(
        self,
        reason_id: UUID,
        changes: dict[str, object],
    ) -> BlockingReason:
        reason = await self._repository.update(reason_id, changes)
        if reason is None:
            raise NotFoundException("Blocking reason not found")
        return reason

    async def deactivate_reason(self, reason_id: UUID) -> None:
        if not await self._repository.deactivate(reason_id):
            raise NotFoundException("Blocking reason not found")
