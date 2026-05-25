from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.config import settings
from app.core.ticket_dependencies import get_ticket_service
from app.schemas.tickets import IncomingB2BEvent
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/b2b", tags=["B2B Events"])


@router.post("/events", status_code=202)
async def receive_b2b_event(
    request: IncomingB2BEvent,
    x_service_key: str = Header(..., alias="X-Service-Key"),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> dict[str, str]:
    if x_service_key != settings.B2B_TO_MOD_SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid service key")
    await ticket_service.apply_b2b_event(
        event_type=request.event_type,
        payload=request.payload,
    )
    return {"status": "accepted"}
