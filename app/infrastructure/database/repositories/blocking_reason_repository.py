from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.ticket import BlockingReason
from app.domain.exceptions import ConflictException
from app.domain.repositories.blocking_reason_repository import (
    AbstractBlockingReasonRepository,
)
from app.infrastructure.database.models.ticket import BlockingReasonModel


class SQLAlchemyBlockingReasonRepository(AbstractBlockingReasonRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        hard_block: bool | None,
        is_active: bool,
    ) -> list[BlockingReason]:
        statement = select(BlockingReasonModel).where(
            BlockingReasonModel.is_active.is_(is_active)
        )
        if hard_block is not None:
            statement = statement.where(
                BlockingReasonModel.hard_block.is_(hard_block)
            )
        result = await self._session.execute(
            statement.order_by(BlockingReasonModel.title.asc())
        )
        return [self._to_entity(model) for model in result.scalars()]

    async def get_by_id(self, reason_id: UUID) -> BlockingReason | None:
        model = await self._session.get(BlockingReasonModel, reason_id)
        return self._to_entity(model) if model is not None else None

    async def get_by_code(self, code: str) -> BlockingReason | None:
        result = await self._session.execute(
            select(BlockingReasonModel).where(BlockingReasonModel.code == code)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model is not None else None

    async def create(
        self,
        *,
        code: str,
        title: str,
        description: str | None,
        hard_block: bool,
    ) -> BlockingReason:
        model = BlockingReasonModel(
            code=code,
            title=title,
            description=description,
            hard_block=hard_block,
            is_active=True,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictException("Blocking reason code already exists") from exc
        await self._session.refresh(model)
        return self._to_entity(model)

    async def update(
        self,
        reason_id: UUID,
        changes: dict[str, object],
    ) -> BlockingReason | None:
        model = await self._session.get(BlockingReasonModel, reason_id)
        if model is None:
            return None
        for field, value in changes.items():
            setattr(model, field, value)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(model)
        return self._to_entity(model)

    async def deactivate(self, reason_id: UUID) -> bool:
        model = await self._session.get(BlockingReasonModel, reason_id)
        if model is None:
            return False
        model.is_active = False
        await self._session.commit()
        return True

    @staticmethod
    def _to_entity(model: BlockingReasonModel) -> BlockingReason:
        return BlockingReason(
            id=model.id,
            code=model.code,
            title=model.title,
            description=model.description,
            hard_block=model.hard_block,
            is_active=model.is_active,
        )
