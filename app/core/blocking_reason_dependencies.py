from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.domain.repositories.blocking_reason_repository import (
    AbstractBlockingReasonRepository,
)
from app.infrastructure.database.repositories.blocking_reason_repository import (
    SQLAlchemyBlockingReasonRepository,
)
from app.services.blocking_reason_service import BlockingReasonService


async def get_blocking_reason_repository(
    db: AsyncSession = Depends(get_db),
) -> AbstractBlockingReasonRepository:
    return SQLAlchemyBlockingReasonRepository(db)


async def get_blocking_reason_service(
    repository: AbstractBlockingReasonRepository = Depends(
        get_blocking_reason_repository
    ),
) -> BlockingReasonService:
    return BlockingReasonService(repository)
