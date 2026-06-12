import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/neomarket"
)
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MOD_TO_B2B_SERVICE_KEY", "test-b2b-key")
os.environ.setdefault("B2B_TO_MOD_SERVICE_KEY", "test-b2b-inbound-key")

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.core.ticket_dependencies import (
    get_b2b_moderation_client,
    get_ticket_repository,
)
from app.domain.entities.ticket import (
    BlockingReason,
    FieldReport,
    ModerationTicket,
    TicketKind,
    TicketStatus,
)
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.main import app
from app.services.b2b_moderation_client import AbstractB2BModerationClient

_TEST_SECRET = "test-secret"
_B2B_INBOUND_KEY = "test-b2b-inbound-key"


def make_token(moderator_id: UUID) -> str:
    payload = {
        "sub": str(moderator_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def auth(moderator_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(moderator_id)}"}


def b2b_headers() -> dict[str, str]:
    return {"X-Service-Key": _B2B_INBOUND_KEY}


class FakeTicketRepository(AbstractTicketRepository):
    def __init__(self, ticket: ModerationTicket | None, reasons: list[BlockingReason]) -> None:
        self.ticket = ticket
        self.reasons = {reason.id: reason for reason in reasons}
        self.field_reports: list[FieldReport] = []
        self.field_reports_cleared = False
        self.saved = False
        self.created: ModerationTicket | None = None
        self.deleted_product_id: UUID | None = None
        self.processed_events: set[UUID] = set()

    async def create(self, ticket: ModerationTicket) -> None:
        self.ticket = ticket
        self.created = ticket

    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        if self.ticket is None or self.ticket.id != ticket_id:
            return None
        return self.ticket

    async def get_by_product_id(self, product_id: UUID) -> ModerationTicket | None:
        if self.ticket is None or self.ticket.product_id != product_id:
            return None
        return self.ticket

    async def get_blocking_reasons(
        self, reason_ids: list[UUID]
    ) -> list[BlockingReason]:
        return [
            self.reasons[reason_id]
            for reason_id in reason_ids
            if reason_id in self.reasons
        ]

    async def save(self, ticket: ModerationTicket) -> None:
        self.ticket = ticket
        self.saved = True

    async def save_field_reports(
        self, ticket_id: UUID, field_reports: list[FieldReport]
    ) -> None:
        self.field_reports = field_reports

    async def clear_field_reports(self, ticket_id: UUID) -> None:
        self.field_reports_cleared = True

    async def delete_by_product_id(self, product_id: UUID) -> None:
        self.deleted_product_id = product_id
        if self.ticket is not None and self.ticket.product_id == product_id:
            self.ticket = None

    async def is_event_processed(self, idempotency_key: UUID) -> bool:
        return idempotency_key in self.processed_events

    async def mark_event_processed(
        self, idempotency_key: UUID, product_id: UUID, occurred_at: datetime
    ) -> bool:
        if idempotency_key in self.processed_events:
            return False
        self.processed_events.add(idempotency_key)
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
        await self.create(ticket)
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
        await self.clear_field_reports(ticket.id)
        await self.save(ticket)
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
        await self.delete_by_product_id(product_id)
        return True


class RecordingB2BClient(AbstractB2BModerationClient):
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_moderated_event(
        self,
        *,
        idempotency_key: UUID,
        product_id: UUID,
        moderator_id: UUID,
        moderator_comment: str | None,
        occurred_at: datetime,
    ) -> None:
        self.events.append({"event_type": "APPROVED"})

    async def send_blocked_event(
        self,
        *,
        idempotency_key: UUID,
        product_id: UUID,
        moderator_id: UUID,
        moderator_comment: str | None,
        blocking_reason_id: UUID,
        hard_block: bool,
        field_reports: list[dict],
        occurred_at: datetime,
    ) -> None:
        self.events.append(
            {
                "idempotency_key": idempotency_key,
                "product_id": product_id,
                "event_type": "BLOCKED",
                "moderator_id": moderator_id,
                "moderator_comment": moderator_comment,
                "blocking_reason_id": blocking_reason_id,
                "hard_block": hard_block,
                "field_reports": field_reports,
                "occurred_at": occurred_at,
            }
        )


def make_ticket(
    *,
    status: TicketStatus = TicketStatus.IN_REVIEW,
    moderator_id: UUID | None = None,
) -> ModerationTicket:
    now = datetime.now(timezone.utc)
    return ModerationTicket(
        id=uuid4(),
        product_id=uuid4(),
        seller_id=uuid4(),
        kind=TicketKind.CREATE,
        status=status,
        queue_priority=1,
        assigned_moderator_id=moderator_id,
        json_after={"skus": [{"id": str(uuid4())}]},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
async def hard_block_client():
    b2b_client = RecordingB2BClient()
    repo_holder: dict[str, FakeTicketRepository] = {}

    def set_repo(ticket: ModerationTicket | None, reasons: list[BlockingReason]):
        repo = FakeTicketRepository(ticket, reasons)
        repo_holder["repo"] = repo
        return repo

    async def override_repository() -> FakeTicketRepository:
        return repo_holder["repo"]

    async def override_b2b_client() -> RecordingB2BClient:
        return b2b_client

    app.dependency_overrides[get_ticket_repository] = override_repository
    app.dependency_overrides[get_b2b_moderation_client] = override_b2b_client

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, set_repo, b2b_client

    app.dependency_overrides.clear()


async def test_hard_block_transitions_to_terminal_and_emits_event(hard_block_client):
    client, set_repo, b2b_client = hard_block_client
    moderator_id = uuid4()
    reason = BlockingReason(id=uuid4(), title="Counterfeit", hard_block=True)
    ticket = make_ticket(moderator_id=moderator_id)
    repo = set_repo(ticket, [reason])

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/block",
        headers=auth(moderator_id),
        json={"blocking_reason_ids": [str(reason.id)], "comment": "confirmed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "HARD_BLOCKED"
    assert repo.ticket.status == TicketStatus.HARD_BLOCKED
    assert repo.ticket.blocking_reason_id == reason.id
    assert repo.ticket.decision_comment == "confirmed"
    assert b2b_client.events[0]["event_type"] == "BLOCKED"
    assert b2b_client.events[0]["hard_block"] is True


async def test_hard_block_event_carries_hard_block_true(hard_block_client):
    client, set_repo, b2b_client = hard_block_client
    moderator_id = uuid4()
    reason = BlockingReason(id=uuid4(), title="Copyright", hard_block=True)
    ticket = make_ticket(moderator_id=moderator_id)
    set_repo(ticket, [reason])

    await client.post(
        f"/api/v1/tickets/{ticket.id}/block",
        headers=auth(moderator_id),
        json={
            "blocking_reason_ids": [str(reason.id)],
            "field_reports": [{"field_path": "title", "message": "fake"}],
        },
    )

    event = b2b_client.events[0]
    assert event["event_type"] == "BLOCKED"
    assert event["blocking_reason_id"] == reason.id
    assert event["hard_block"] is True
    assert event["field_reports"] == [
        {"field_name": "title", "sku_id": None, "comment": "fake"}
    ]


async def test_any_modify_on_hard_blocked_returns_403(hard_block_client):
    client, set_repo, b2b_client = hard_block_client
    moderator_id = uuid4()
    reason = BlockingReason(id=uuid4(), title="Counterfeit", hard_block=True)
    ticket = make_ticket(status=TicketStatus.HARD_BLOCKED, moderator_id=moderator_id)
    set_repo(ticket, [reason])

    approve_response = await client.post(
        f"/api/v1/tickets/{ticket.id}/approve",
        headers=auth(moderator_id),
        json={"comment": "try"},
    )
    block_response = await client.post(
        f"/api/v1/tickets/{ticket.id}/block",
        headers=auth(moderator_id),
        json={"blocking_reason_ids": [str(reason.id)]},
    )

    assert approve_response.status_code == 403
    assert block_response.status_code == 403
    assert ticket.status == TicketStatus.HARD_BLOCKED
    assert b2b_client.events == []


async def test_edited_event_on_hard_blocked_is_ignored(hard_block_client):
    client, set_repo, _b2b_client = hard_block_client
    moderator_id = uuid4()
    reason = BlockingReason(id=uuid4(), title="Counterfeit", hard_block=True)
    ticket = make_ticket(status=TicketStatus.HARD_BLOCKED, moderator_id=moderator_id)
    repo = set_repo(ticket, [reason])

    response = await client.post(
        "/api/v1/b2b/events",
        headers=b2b_headers(),
        json={
            "event_type": "PRODUCT_EDITED",
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "product_id": str(ticket.product_id),
                "seller_id": str(ticket.seller_id),
                "json_before": {"title": "old"},
                "json_after": {"title": "new", "skus": []},
            },
        },
    )

    assert response.status_code == 202
    assert repo.ticket.status == TicketStatus.HARD_BLOCKED
    assert repo.saved is False


async def test_deleted_event_removes_hard_blocked(hard_block_client):
    client, set_repo, _b2b_client = hard_block_client
    moderator_id = uuid4()
    reason = BlockingReason(id=uuid4(), title="Counterfeit", hard_block=True)
    ticket = make_ticket(status=TicketStatus.HARD_BLOCKED, moderator_id=moderator_id)
    repo = set_repo(ticket, [reason])

    response = await client.post(
        "/api/v1/b2b/events",
        headers=b2b_headers(),
        json={
            "event_type": "PRODUCT_DELETED",
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"product_id": str(ticket.product_id)},
        },
    )

    assert response.status_code == 202
    assert repo.ticket is None
    assert repo.deleted_product_id == ticket.product_id


async def test_created_event_creates_pending_ticket(hard_block_client):
    client, set_repo, _b2b_client = hard_block_client
    repo = set_repo(None, [])
    product_id = uuid4()
    seller_id = uuid4()
    category_id = uuid4()

    response = await client.post(
        "/api/v1/b2b/events",
        headers=b2b_headers(),
        json={
            "event_type": "PRODUCT_CREATED",
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "product_id": str(product_id),
                "seller_id": str(seller_id),
                "category_id": str(category_id),
                "queue_priority": 2,
                "json_after": {"title": "New product", "skus": [{"id": str(uuid4())}]},
            },
        },
    )

    assert response.status_code == 202
    assert repo.created is not None
    assert repo.created.product_id == product_id
    assert repo.created.seller_id == seller_id
    assert repo.created.category_id == category_id
    assert repo.created.status == TicketStatus.PENDING
    assert repo.created.kind == TicketKind.CREATE
    assert repo.created.queue_priority == 2


async def test_b2b_events_rejects_invalid_service_key(hard_block_client):
    client, set_repo, _b2b_client = hard_block_client
    ticket = make_ticket(status=TicketStatus.HARD_BLOCKED)
    set_repo(ticket, [])

    response = await client.post(
        "/api/v1/b2b/events",
        headers={"X-Service-Key": "wrong-key"},
        json={
            "event_type": "PRODUCT_DELETED",
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"product_id": str(ticket.product_id)},
        },
    )

    assert response.status_code == 401
