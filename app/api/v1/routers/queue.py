from uuid import UUID

from fastapi import APIRouter, Body, Depends, Response, status

from app.api.v1.dependencies.auth import get_current_moderator_id
from app.core.ticket_dependencies import get_ticket_service
from app.schemas.tickets import ClaimQueueRequest, TicketResponse
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/queue", tags=["Queue"])


@router.post(
    "/claim",
    response_model=TicketResponse,
    responses={status.HTTP_204_NO_CONTENT: {"description": "Queue is empty"}},
)
async def claim_next_ticket(
    request: ClaimQueueRequest = Body(default_factory=ClaimQueueRequest),
    moderator_id: UUID = Depends(get_current_moderator_id),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TicketResponse | Response:
    ticket = await ticket_service.claim_next_ticket(
        moderator_id=moderator_id,
        queue_priority=request.queue_priority,
        category_ids=request.category_ids,
    )
    if ticket is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return TicketResponse.from_entity(ticket)
