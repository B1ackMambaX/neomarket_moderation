from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.v1.dependencies.auth import get_current_moderator_id
from app.core.ticket_dependencies import get_ticket_service
from app.schemas.tickets import (
    ApproveTicketRequest,
    BlockTicketRequest,
    TicketResponse,
)
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post("/{ticket_id}/approve", response_model=TicketResponse)
async def approve_ticket(
    ticket_id: UUID,
    request: ApproveTicketRequest | None = None,
    moderator_id: UUID = Depends(get_current_moderator_id),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TicketResponse:
    ticket = await ticket_service.approve_ticket(
        ticket_id=ticket_id,
        moderator_id=moderator_id,
        comment=request.comment if request is not None else None,
    )
    return TicketResponse.from_entity(ticket)


@router.post("/{ticket_id}/block", response_model=TicketResponse)
async def block_ticket(
    ticket_id: UUID,
    request: BlockTicketRequest,
    moderator_id: UUID = Depends(get_current_moderator_id),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TicketResponse:
    ticket = await ticket_service.block_ticket(
        ticket_id=ticket_id,
        moderator_id=moderator_id,
        blocking_reason_ids=request.blocking_reason_ids,
        comment=request.comment,
        field_reports=[report.to_entity() for report in request.field_reports],
    )
    return TicketResponse.from_entity(ticket)

