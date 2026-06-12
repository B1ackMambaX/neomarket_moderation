from secrets import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.config import settings
from app.core.ticket_dependencies import get_ticket_service
from app.schemas.tickets import IncomingB2BEvent, ProductEventRequest
from app.services.ticket_service import TicketService

router = APIRouter(tags=["B2B Events"])


def authorize_service(x_service_key: str | None) -> None:
    if x_service_key is None or not compare_digest(
        x_service_key, settings.B2B_TO_MOD_SERVICE_KEY
    ):
        raise HTTPException(status_code=401, detail="Invalid service key")


@router.post("/events/product", status_code=200)
async def receive_product_event(
    request: ProductEventRequest,
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> dict[str, str]:
    authorize_service(x_service_key)
    await ticket_service.apply_b2b_event(
        event_type=request.event,
        idempotency_key=request.idempotency_key,
        occurred_at=request.date,
        product_id=request.product_id,
        seller_id=request.seller_id,
    )
    return {"status": "accepted"}


@router.post("/b2b/events", status_code=202, include_in_schema=False)
async def receive_b2b_event(
    request: IncomingB2BEvent,
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> dict[str, str]:
    authorize_service(x_service_key)
    await ticket_service.apply_b2b_event(
        event_type=request.event_type.removeprefix("PRODUCT_"),
        idempotency_key=request.idempotency_key,
        occurred_at=request.occurred_at,
        product_id=request.payload["product_id"],
        seller_id=request.payload.get("seller_id"),
        payload=request.payload,
    )
    return {"status": "accepted"}
