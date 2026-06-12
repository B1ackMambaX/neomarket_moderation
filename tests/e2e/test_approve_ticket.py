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
from app.domain.entities.ticket import ModerationTicket, TicketKind, TicketStatus
from app.domain.repositories.ticket_repository import AbstractTicketRepository
from app.main import app
from app.services.b2b_moderation_client import AbstractB2BModerationClient

_TEST_SECRET = "test-secret"


def make_token(moderator_id: UUID) -> str:
    payload = {
        "sub": str(moderator_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def auth(moderator_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(moderator_id)}"}


class FakeTicketRepository(AbstractTicketRepository):
    def __init__(self, ticket: ModerationTicket | None) -> None:
        self.ticket = ticket
        self.field_reports_cleared = False
        self.saved = False

    async def create(self, ticket: ModerationTicket) -> None:
        self.ticket = ticket

    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        if self.ticket is None or self.ticket.id != ticket_id:
            return None
        return self.ticket

    async def get_by_product_id(self, product_id: UUID) -> ModerationTicket | None:
        if self.ticket is None or self.ticket.product_id != product_id:
            return None
        return self.ticket

    async def claim_next(self, **kwargs):
        raise NotImplementedError

    async def get_blocking_reasons(self, reason_ids: list[UUID]) -> list:
        return []

    async def save(self, ticket: ModerationTicket) -> None:
        self.ticket = ticket
        self.saved = True

    async def save_field_reports(self, ticket_id: UUID, field_reports: list) -> None:
        pass

    async def clear_field_reports(self, ticket_id: UUID) -> None:
        self.field_reports_cleared = True

    async def delete_by_product_id(self, product_id: UUID) -> None:
        self.ticket = None


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
        self.events.append(
            {
                "idempotency_key": idempotency_key,
                "product_id": product_id,
                "event_type": "APPROVED",
                "moderator_id": moderator_id,
                "moderator_comment": moderator_comment,
                "occurred_at": occurred_at,
            }
        )

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
    skus: list[dict] | None = None,
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
        json_after={"skus": skus if skus is not None else [{"id": str(uuid4())}]},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
async def approve_client():
    b2b_client = RecordingB2BClient()
    repo_holder: dict[str, FakeTicketRepository] = {}

    def set_ticket(ticket: ModerationTicket) -> FakeTicketRepository:
        repo = FakeTicketRepository(ticket)
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
        yield client, set_ticket, b2b_client

    app.dependency_overrides.clear()


async def test_approve_transitions_to_moderated_and_emits_event(approve_client):
    client, set_ticket, b2b_client = approve_client
    moderator_id = uuid4()
    ticket = make_ticket(moderator_id=moderator_id)
    repo = set_ticket(ticket)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/approve",
        headers=auth(moderator_id),
        json={"comment": "ok"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "APPROVED"
    assert data["product_id"] == str(ticket.product_id)
    assert repo.ticket.status == TicketStatus.APPROVED
    assert repo.ticket.decision_comment == "ok"
    assert repo.field_reports_cleared is True
    assert repo.saved is True
    assert b2b_client.events == [
        {
            "idempotency_key": ticket.id,
            "product_id": ticket.product_id,
            "event_type": "APPROVED",
            "moderator_id": moderator_id,
            "moderator_comment": "ok",
            "occurred_at": repo.ticket.decision_at,
        }
    ]


async def test_approve_others_card_returns_403(approve_client):
    client, set_ticket, b2b_client = approve_client
    ticket = make_ticket(moderator_id=uuid4())
    set_ticket(ticket)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/approve",
        headers=auth(uuid4()),
        json={},
    )

    assert response.status_code == 403
    assert ticket.status == TicketStatus.IN_REVIEW
    assert b2b_client.events == []


async def test_approve_after_edited_returns_409(approve_client):
    client, set_ticket, b2b_client = approve_client
    moderator_id = uuid4()
    # Product was edited during review — ticket went back to PENDING (new revision)
    ticket = make_ticket(status=TicketStatus.PENDING, moderator_id=moderator_id)
    set_ticket(ticket)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/approve",
        headers=auth(moderator_id),
        json={},
    )

    assert response.status_code == 409
    assert ticket.status == TicketStatus.PENDING
    assert b2b_client.events == []


async def test_approve_without_sku_returns_409(approve_client):
    client, set_ticket, b2b_client = approve_client
    moderator_id = uuid4()
    ticket = make_ticket(moderator_id=moderator_id, skus=[])
    set_ticket(ticket)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/approve",
        headers=auth(moderator_id),
        json={},
    )

    assert response.status_code == 409
    assert ticket.status == TicketStatus.IN_REVIEW
    assert b2b_client.events == []
