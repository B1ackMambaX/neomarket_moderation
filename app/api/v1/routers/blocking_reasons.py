from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.v1.dependencies.auth import get_current_moderator_id, require_admin
from app.core.blocking_reason_dependencies import get_blocking_reason_service
from app.schemas.blocking_reasons import (
    BlockingReasonCreateRequest,
    BlockingReasonResponse,
    BlockingReasonUpdateRequest,
)
from app.services.blocking_reason_service import BlockingReasonService

router = APIRouter(
    prefix="/blocking-reasons",
    tags=["BlockingReasons"],
)


@router.get(
    "",
    response_model=list[BlockingReasonResponse],
    dependencies=[Depends(get_current_moderator_id)],
)
async def list_blocking_reasons(
    hard_block: Annotated[bool | None, Query()] = None,
    is_active: Annotated[bool, Query()] = True,
    service: BlockingReasonService = Depends(get_blocking_reason_service),
) -> list[BlockingReasonResponse]:
    reasons = await service.list_reasons(
        hard_block=hard_block,
        is_active=is_active,
    )
    return [BlockingReasonResponse.model_validate(reason) for reason in reasons]


@router.post(
    "",
    response_model=BlockingReasonResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_blocking_reason(
    request: BlockingReasonCreateRequest,
    service: BlockingReasonService = Depends(get_blocking_reason_service),
) -> BlockingReasonResponse:
    reason = await service.create_reason(**request.model_dump())
    return BlockingReasonResponse.model_validate(reason)


@router.patch(
    "/{reason_id}",
    response_model=BlockingReasonResponse,
    dependencies=[Depends(require_admin)],
)
async def update_blocking_reason(
    reason_id: UUID,
    request: BlockingReasonUpdateRequest,
    service: BlockingReasonService = Depends(get_blocking_reason_service),
) -> BlockingReasonResponse:
    reason = await service.update_reason(
        reason_id,
        request.model_dump(exclude_unset=True),
    )
    return BlockingReasonResponse.model_validate(reason)


@router.delete(
    "/{reason_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def deactivate_blocking_reason(
    reason_id: UUID,
    service: BlockingReasonService = Depends(get_blocking_reason_service),
) -> Response:
    await service.deactivate_reason(reason_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
