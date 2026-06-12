import asyncio
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
from app.domain.repositories.ticket_repository import (
    AbstractTicketRepository,
    ClaimNextResult,
)
from app.main import app
from app.services.b2b_moderation_client import AbstractB2BModerationClient

_TEST_SECRET = "test-secret"


def auth(moderator_id: UUID) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": str(moderator_id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        _TEST_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def make_ticket(
    *,
    priority: int = 1,
    created_at: datetime | None = None,
    category_id: UUID | None = None,
) -> ModerationTicket:
    now = created_at or datetime.now(timezone.utc)
    return ModerationTicket(
        id=uuid4(),
        product_id=uuid4(),
        seller_id=uuid4(),
        category_id=category_id,
        kind=TicketKind.CREATE,
        status=TicketStatus.PENDING,
        queue_priority=priority,
        json_after={"skus": []},
        created_at=now,
        updated_at=now,
    )


class ClaimingFakeTicketRepository(AbstractTicketRepository):
    def __init__(self, tickets: list[ModerationTicket]) -> None:
        self.tickets = tickets
        self._lock = asyncio.Lock()

    async def claim_next(
        self,
        *,
        moderator_id: UUID,
        queue_priority: int | None,
        category_ids: list[UUID] | None,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> ClaimNextResult:
        async with self._lock:
            for ticket in self.tickets:
                if (
                    ticket.status == TicketStatus.IN_REVIEW
                    and ticket.claim_expires_at is not None
                    and ticket.claim_expires_at <= claimed_at
                ):
                    ticket.status = TicketStatus.PENDING
                    ticket.assigned_moderator_id = None
                    ticket.claimed_at = None
                    ticket.claim_expires_at = None

            if any(
                ticket.status == TicketStatus.IN_REVIEW
                and ticket.assigned_moderator_id == moderator_id
                for ticket in self.tickets
            ):
                return ClaimNextResult(moderator_already_has_ticket=True)

            candidates = [
                ticket
                for ticket in self.tickets
                if ticket.status == TicketStatus.PENDING
                and (
                    queue_priority is None
                    or ticket.queue_priority == queue_priority
                )
                and (
                    not category_ids
                    or ticket.category_id in category_ids
                )
            ]
            candidates.sort(key=lambda ticket: (ticket.queue_priority, ticket.created_at))
            if not candidates:
                return ClaimNextResult()

            ticket = candidates[0]
            ticket.status = TicketStatus.IN_REVIEW
            ticket.assigned_moderator_id = moderator_id
            ticket.claimed_at = claimed_at
            ticket.claim_expires_at = claim_expires_at
            ticket.updated_at = claimed_at
            return ClaimNextResult(ticket=ticket)

    async def create(self, ticket: ModerationTicket) -> None:
        self.tickets.append(ticket)

    async def get_by_id(self, ticket_id: UUID) -> ModerationTicket | None:
        return next((ticket for ticket in self.tickets if ticket.id == ticket_id), None)

    async def get_by_product_id(self, product_id: UUID) -> ModerationTicket | None:
        return next(
            (ticket for ticket in self.tickets if ticket.product_id == product_id),
            None,
        )

    async def get_blocking_reasons(self, reason_ids: list[UUID]) -> list:
        return []

    async def save(self, ticket: ModerationTicket) -> None:
        pass

    async def save_field_reports(self, ticket_id: UUID, field_reports: list) -> None:
        pass

    async def clear_field_reports(self, ticket_id: UUID) -> None:
        pass

    async def delete_by_product_id(self, product_id: UUID) -> None:
        self.tickets = [
            ticket for ticket in self.tickets if ticket.product_id != product_id
        ]


class NoopB2BClient(AbstractB2BModerationClient):
    async def get_product(self, product_id: UUID) -> dict:
        return {}

    async def send_moderated_event(self, **kwargs) -> None:
        pass

    async def send_blocked_event(self, **kwargs) -> None:
        pass


@pytest.fixture
async def claim_client():
    repository = ClaimingFakeTicketRepository([])

    async def override_repository() -> ClaimingFakeTicketRepository:
        return repository

    async def override_b2b_client() -> NoopB2BClient:
        return NoopB2BClient()

    app.dependency_overrides[get_ticket_repository] = override_repository
    app.dependency_overrides[get_b2b_moderation_client] = override_b2b_client

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, repository

    app.dependency_overrides.clear()


async def test_next_returns_oldest_pending(claim_client):
    client, repository = claim_client
    moderator_id = uuid4()
    now = datetime.now(timezone.utc)
    oldest = make_ticket(created_at=now - timedelta(minutes=2))
    repository.tickets = [make_ticket(created_at=now), oldest]

    response = await client.post("/api/v1/queue/claim", headers=auth(moderator_id))

    assert response.status_code == 200
    assert response.json()["id"] == str(oldest.id)
    assert oldest.status == TicketStatus.IN_REVIEW
    assert oldest.assigned_moderator_id == moderator_id
    assert oldest.claim_expires_at > oldest.claimed_at


async def test_concurrent_two_moderators_get_different_cards(claim_client):
    client, repository = claim_client
    repository.tickets = [make_ticket(), make_ticket()]

    first, second = await asyncio.gather(
        client.post("/api/v1/queue/claim", headers=auth(uuid4())),
        client.post("/api/v1/queue/claim", headers=auth(uuid4())),
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] != second.json()["id"]


async def test_empty_queue_returns_204(claim_client):
    client, _repository = claim_client

    response = await client.post("/api/v1/queue/claim", headers=auth(uuid4()))

    assert response.status_code == 204
    assert response.content == b""


async def test_moderator_already_has_in_review_returns_409(claim_client):
    client, repository = claim_client
    moderator_id = uuid4()
    active = make_ticket()
    active.status = TicketStatus.IN_REVIEW
    active.assigned_moderator_id = moderator_id
    active.claimed_at = datetime.now(timezone.utc)
    active.claim_expires_at = active.claimed_at + timedelta(minutes=30)
    repository.tickets = [active, make_ticket()]

    response = await client.post("/api/v1/queue/claim", headers=auth(moderator_id))

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


async def test_concurrent_same_moderator_claims_only_one_card(claim_client):
    client, repository = claim_client
    moderator_id = uuid4()
    repository.tickets = [make_ticket(), make_ticket()]

    first, second = await asyncio.gather(
        client.post("/api/v1/queue/claim", headers=auth(moderator_id)),
        client.post("/api/v1/queue/claim", headers=auth(moderator_id)),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert sum(
        ticket.assigned_moderator_id == moderator_id
        for ticket in repository.tickets
    ) == 1


async def test_auto_priority_and_expired_claim_returns_to_queue(claim_client):
    client, repository = claim_client
    expired = make_ticket(priority=1)
    expired.status = TicketStatus.IN_REVIEW
    expired.assigned_moderator_id = uuid4()
    expired.claimed_at = datetime.now(timezone.utc) - timedelta(hours=1)
    expired.claim_expires_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    repository.tickets = [make_ticket(priority=2), expired]

    response = await client.post("/api/v1/queue/claim", headers=auth(uuid4()))

    assert response.status_code == 200
    assert response.json()["id"] == str(expired.id)


async def test_queue_and_category_filters(claim_client):
    client, repository = claim_client
    category_id = uuid4()
    expected = make_ticket(priority=3, category_id=category_id)
    repository.tickets = [
        make_ticket(priority=1),
        expected,
        make_ticket(priority=3),
    ]

    response = await client.post(
        "/api/v1/queue/claim",
        headers=auth(uuid4()),
        json={"queue_priority": 3, "category_ids": [str(category_id)]},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(expected.id)
