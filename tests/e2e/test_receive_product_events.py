import os
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/neomarket"
)
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MOD_TO_B2B_SERVICE_KEY", "test-b2b-key")
os.environ.setdefault("B2B_TO_MOD_SERVICE_KEY", "test-b2b-inbound-key")

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.ticket_dependencies import (
    get_b2b_moderation_client,
    get_ticket_repository,
)
from app.domain.entities.ticket import ModerationTicket, TicketKind, TicketStatus
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.main import app
from app.services.b2b_moderation_client import AbstractB2BModerationClient

_SERVICE_HEADERS = {"X-Service-Key": "test-b2b-inbound-key"}


class FakeTicketRepository(AbstractTicketRepository):
    def __init__(self) -> None:
        self.ticket: ModerationTicket | None = None
        self.processed_events: set[UUID] = set()
        self.write_count = 0
        self.field_reports_cleared = False

    async def create(self, ticket: ModerationTicket) -> None:
        self.ticket = ticket

    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        if self.ticket is not None and self.ticket.id == ticket_id:
            return self.ticket
        return None

    async def get_by_product_id(self, product_id: UUID) -> ModerationTicket | None:
        if self.ticket is not None and self.ticket.product_id == product_id:
            return self.ticket
        return None

    async def claim_next(self, **kwargs):
        raise NotImplementedError

    async def get_blocking_reasons(self, reason_ids: list[UUID]) -> list:
        return []

    async def save(self, ticket: ModerationTicket) -> None:
        self.ticket = ticket

    async def save_field_reports(self, ticket_id: UUID, field_reports: list) -> None:
        pass

    async def clear_field_reports(self, ticket_id: UUID) -> None:
        self.field_reports_cleared = True

    async def delete_by_product_id(self, product_id: UUID) -> None:
        self.ticket = None

    async def is_event_processed(self, idempotency_key: UUID) -> bool:
        return idempotency_key in self.processed_events

    async def mark_event_processed(
        self, idempotency_key: UUID, product_id: UUID, occurred_at: datetime
    ) -> bool:
        if idempotency_key in self.processed_events:
            return False
        self.processed_events.add(idempotency_key)
        self.write_count += 1
        return True

    async def create_from_event(
        self,
        ticket: ModerationTicket,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        if not await self.mark_event_processed(
            idempotency_key, ticket.product_id, occurred_at
        ):
            return False
        self.ticket = ticket
        return True

    async def save_from_event(
        self,
        ticket: ModerationTicket,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        if not await self.mark_event_processed(
            idempotency_key, ticket.product_id, occurred_at
        ):
            return False
        self.ticket = ticket
        self.field_reports_cleared = True
        return True

    async def delete_from_event(
        self,
        product_id: UUID,
        idempotency_key: UUID,
        occurred_at: datetime,
    ) -> bool:
        if not await self.mark_event_processed(
            idempotency_key, product_id, occurred_at
        ):
            return False
        self.ticket = None
        return True


class ProductB2BClient(AbstractB2BModerationClient):
    def __init__(self) -> None:
        self.products: dict[UUID, dict] = {}
        self.get_calls: list[UUID] = []

    async def get_product(self, product_id: UUID) -> dict:
        self.get_calls.append(product_id)
        return deepcopy(self.products[product_id])

    async def send_moderated_event(self, **kwargs) -> None:
        pass

    async def send_blocked_event(self, **kwargs) -> None:
        pass


def event_body(
    product_id: UUID,
    seller_id: UUID,
    event: str,
    idempotency_key: UUID | None = None,
) -> dict:
    return {
        "idempotency_key": str(idempotency_key or uuid4()),
        "product_id": str(product_id),
        "seller_id": str(seller_id),
        "event": event,
        "date": datetime.now(timezone.utc).isoformat(),
    }


def make_ticket(status: TicketStatus, priority: int = 1) -> ModerationTicket:
    now = datetime.now(timezone.utc)
    return ModerationTicket(
        id=uuid4(),
        product_id=uuid4(),
        seller_id=uuid4(),
        kind=TicketKind.CREATE,
        status=status,
        queue_priority=priority,
        assigned_moderator_id=uuid4(),
        claimed_at=now,
        claim_expires_at=now,
        json_after={"title": "before", "skus": []},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
async def product_event_client():
    repository = FakeTicketRepository()
    b2b_client = ProductB2BClient()

    async def override_repository() -> FakeTicketRepository:
        return repository

    async def override_b2b_client() -> ProductB2BClient:
        return b2b_client

    app.dependency_overrides[get_ticket_repository] = override_repository
    app.dependency_overrides[get_b2b_moderation_client] = override_b2b_client

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, repository, b2b_client

    app.dependency_overrides.clear()


async def test_created_pending(product_event_client):
    client, repository, b2b_client = product_event_client
    product_id, seller_id, category_id = uuid4(), uuid4(), uuid4()
    b2b_client.products[product_id] = {
        "id": str(product_id),
        "seller_id": str(seller_id),
        "category_id": str(category_id),
        "title": "created",
        "skus": [],
    }

    response = await client.post(
        "/api/v1/events/product",
        headers=_SERVICE_HEADERS,
        json=event_body(product_id, seller_id, "CREATED"),
    )

    assert response.status_code == 200
    assert repository.ticket is not None
    assert repository.ticket.status == TicketStatus.PENDING
    assert repository.ticket.queue_priority == 1
    assert repository.ticket.json_before is None
    assert repository.ticket.json_after["title"] == "created"


@pytest.mark.parametrize(
    ("old_status", "expected_priority"),
    [(TicketStatus.APPROVED, 3), (TicketStatus.BLOCKED, 2)],
)
async def test_edited_returns_to_review(
    product_event_client, old_status, expected_priority
):
    client, repository, b2b_client = product_event_client
    ticket = make_ticket(old_status)
    repository.ticket = ticket
    b2b_client.products[ticket.product_id] = {
        "category_id": str(uuid4()),
        "title": "after",
        "total_active_quantity": 5,
        "skus": [],
    }

    response = await client.post(
        "/api/v1/events/product",
        headers=_SERVICE_HEADERS,
        json=event_body(ticket.product_id, ticket.seller_id, "EDITED"),
    )

    assert response.status_code == 200
    assert ticket.status == TicketStatus.PENDING
    assert ticket.kind == TicketKind.EDIT
    assert ticket.queue_priority == expected_priority
    assert ticket.assigned_moderator_id is None
    assert ticket.json_before["title"] == "before"
    assert ticket.json_after["title"] == "after"


async def test_edited_updates_in_review(product_event_client):
    client, repository, b2b_client = product_event_client
    ticket = make_ticket(TicketStatus.IN_REVIEW, priority=4)
    repository.ticket = ticket
    b2b_client.products[ticket.product_id] = {
        "category_id": str(uuid4()),
        "title": "changed during review",
        "skus": [],
    }

    response = await client.post(
        "/api/v1/events/product",
        headers=_SERVICE_HEADERS,
        json=event_body(ticket.product_id, ticket.seller_id, "EDITED"),
    )

    assert response.status_code == 200
    assert ticket.status == TicketStatus.PENDING
    assert ticket.queue_priority == 4
    assert ticket.json_after["title"] == "changed during review"
    assert repository.field_reports_cleared is True


async def test_deleted_archived(product_event_client):
    client, repository, _b2b_client = product_event_client
    ticket = make_ticket(TicketStatus.PENDING)
    repository.ticket = ticket

    response = await client.post(
        "/api/v1/events/product",
        headers=_SERVICE_HEADERS,
        json=event_body(ticket.product_id, ticket.seller_id, "DELETED"),
    )

    assert response.status_code == 200
    assert repository.ticket is None


async def test_duplicate_event_no_side_effects(product_event_client):
    client, repository, b2b_client = product_event_client
    product_id, seller_id, event_key = uuid4(), uuid4(), uuid4()
    b2b_client.products[product_id] = {
        "category_id": str(uuid4()),
        "title": "created",
        "skus": [],
    }
    body = event_body(product_id, seller_id, "CREATED", event_key)

    first = await client.post(
        "/api/v1/events/product", headers=_SERVICE_HEADERS, json=body
    )
    ticket_id = repository.ticket.id
    second = await client.post(
        "/api/v1/events/product", headers=_SERVICE_HEADERS, json=body
    )

    assert first.status_code == second.status_code == 200
    assert repository.ticket.id == ticket_id
    assert repository.write_count == 1
    assert b2b_client.get_calls == [product_id]


async def test_missing_service_header_401(product_event_client):
    client, repository, b2b_client = product_event_client
    product_id, seller_id = uuid4(), uuid4()

    response = await client.post(
        "/api/v1/events/product",
        json=event_body(product_id, seller_id, "CREATED"),
    )

    assert response.status_code == 401
    assert repository.ticket is None
    assert b2b_client.get_calls == []
