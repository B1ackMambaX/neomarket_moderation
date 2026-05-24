from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.core.config import settings


class B2BModerationClientError(Exception):
    pass


class AbstractB2BModerationClient(ABC):
    @abstractmethod
    async def send_moderated_event(
        self,
        *,
        idempotency_key: UUID,
        product_id: UUID,
        moderator_id: UUID,
        moderator_comment: str | None,
        occurred_at: datetime,
    ) -> None:
        raise NotImplementedError


class HttpB2BModerationClient(AbstractB2BModerationClient):
    async def send_moderated_event(
        self,
        *,
        idempotency_key: UUID,
        product_id: UUID,
        moderator_id: UUID,
        moderator_comment: str | None,
        occurred_at: datetime,
    ) -> None:
        payload = {
            "idempotency_key": str(idempotency_key),
            "product_id": str(product_id),
            "event_type": "MODERATED",
            "moderator_id": str(moderator_id),
            "moderator_comment": moderator_comment,
            "blocking_reason_id": None,
            "hard_block": False,
            "field_reports": None,
            "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        }
        headers = {"X-Service-Key": settings.MOD_TO_B2B_SERVICE_KEY}
        url = f"{settings.B2B_BASE_URL.rstrip('/')}/api/v1/moderation/events"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            raise B2BModerationClientError(
                f"B2B moderation event rejected with {response.status_code}"
            )
