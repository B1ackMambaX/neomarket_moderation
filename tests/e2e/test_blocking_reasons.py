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

from app.core.blocking_reason_dependencies import get_blocking_reason_repository
from app.domain.entities.ticket import BlockingReason
from app.domain.repositories.blocking_reason_repository import (
    AbstractBlockingReasonRepository,
)
from app.infrastructure.database.models.ticket import ModerationTicketModel
from app.main import app

_TEST_SECRET = "test-secret"


def auth(*, admin: bool = False) -> dict[str, str]:
    payload: dict = {
        "sub": str(uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    if admin:
        payload["role"] = "admin"
    token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


class FakeBlockingReasonRepository(AbstractBlockingReasonRepository):
    def __init__(self, reasons: list[BlockingReason]) -> None:
        self.reasons = {reason.id: reason for reason in reasons}

    async def list(
        self,
        *,
        hard_block: bool | None,
        is_active: bool,
    ) -> list[BlockingReason]:
        reasons = [
            reason
            for reason in self.reasons.values()
            if reason.is_active == is_active
            and (hard_block is None or reason.hard_block == hard_block)
        ]
        return sorted(reasons, key=lambda reason: reason.title)

    async def get_by_id(self, reason_id: UUID) -> BlockingReason | None:
        return self.reasons.get(reason_id)

    async def get_by_code(self, code: str) -> BlockingReason | None:
        return next(
            (reason for reason in self.reasons.values() if reason.code == code),
            None,
        )

    async def create(
        self,
        *,
        code: str,
        title: str,
        description: str | None,
        hard_block: bool,
    ) -> BlockingReason:
        reason = BlockingReason(
            id=uuid4(),
            code=code,
            title=title,
            description=description,
            hard_block=hard_block,
        )
        self.reasons[reason.id] = reason
        return reason

    async def update(
        self,
        reason_id: UUID,
        changes: dict[str, object],
    ) -> BlockingReason | None:
        reason = self.reasons.get(reason_id)
        if reason is None:
            return None
        updated = BlockingReason(
            id=reason.id,
            code=reason.code,
            title=str(changes.get("title", reason.title)),
            description=changes.get("description", reason.description),
            hard_block=reason.hard_block,
            is_active=bool(changes.get("is_active", reason.is_active)),
        )
        self.reasons[reason_id] = updated
        return updated

    async def deactivate(self, reason_id: UUID) -> bool:
        reason = self.reasons.get(reason_id)
        if reason is None:
            return False
        self.reasons[reason_id] = BlockingReason(
            id=reason.id,
            code=reason.code,
            title=reason.title,
            description=reason.description,
            hard_block=reason.hard_block,
            is_active=False,
        )
        return True


def make_reason(
    *,
    code: str,
    title: str,
    hard_block: bool,
    is_active: bool = True,
) -> BlockingReason:
    return BlockingReason(
        id=uuid4(),
        code=code,
        title=title,
        hard_block=hard_block,
        is_active=is_active,
    )


@pytest.fixture
async def blocking_reasons_client():
    repository = FakeBlockingReasonRepository([])

    async def override_repository() -> FakeBlockingReasonRepository:
        return repository

    app.dependency_overrides[get_blocking_reason_repository] = override_repository
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, repository
    app.dependency_overrides.clear()


async def test_list_returns_active_reasons(blocking_reasons_client):
    client, repository = blocking_reasons_client
    soft = make_reason(code="BAD_IMAGE", title="Bad image", hard_block=False)
    hard = make_reason(code="COUNTERFEIT", title="Counterfeit", hard_block=True)
    repository.reasons = {soft.id: soft, hard.id: hard}

    response = await client.get("/api/v1/blocking-reasons", headers=auth())

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(soft.id),
            "code": "BAD_IMAGE",
            "title": "Bad image",
            "description": None,
            "hard_block": False,
            "is_active": True,
        },
        {
            "id": str(hard.id),
            "code": "COUNTERFEIT",
            "title": "Counterfeit",
            "description": None,
            "hard_block": True,
            "is_active": True,
        },
    ]


async def test_inactive_reasons_not_visible(blocking_reasons_client):
    client, repository = blocking_reasons_client
    active = make_reason(code="ACTIVE", title="Active", hard_block=False)
    inactive = make_reason(
        code="INACTIVE",
        title="Inactive",
        hard_block=False,
        is_active=False,
    )
    repository.reasons = {active.id: active, inactive.id: inactive}

    response = await client.get("/api/v1/blocking-reasons", headers=auth())

    assert response.status_code == 200
    assert [reason["id"] for reason in response.json()] == [str(active.id)]


async def test_list_filters_by_hard_block(blocking_reasons_client):
    client, repository = blocking_reasons_client
    soft = make_reason(code="SOFT", title="Soft", hard_block=False)
    hard = make_reason(code="HARD", title="Hard", hard_block=True)
    repository.reasons = {soft.id: soft, hard.id: hard}

    response = await client.get(
        "/api/v1/blocking-reasons?hard_block=true",
        headers=auth(),
    )

    assert response.status_code == 200
    assert [reason["id"] for reason in response.json()] == [str(hard.id)]


async def test_referenced_reason_cannot_be_deleted(blocking_reasons_client):
    """DELETE endpoint soft-deactivates; DB-level hard delete is blocked by FK RESTRICT."""
    client, repository = blocking_reasons_client
    referenced_reason = make_reason(
        code="REFERENCED",
        title="Referenced",
        hard_block=False,
    )
    repository.reasons = {referenced_reason.id: referenced_reason}

    response = await client.delete(
        f"/api/v1/blocking-reasons/{referenced_reason.id}",
        headers=auth(admin=True),
    )

    # API never hard-deletes: record stays, only is_active flips to False.
    assert response.status_code == 204
    assert referenced_reason.id in repository.reasons
    assert repository.reasons[referenced_reason.id].is_active is False


def test_fk_restrict_prevents_hard_delete():
    """Structural: ORM FK is ON DELETE RESTRICT, blocking accidental raw SQL deletes."""
    foreign_key = next(
        iter(ModerationTicketModel.__table__.c.blocking_reason_id.foreign_keys)
    )
    assert foreign_key.target_fullname == "blocking_reasons.id"
    assert foreign_key.ondelete == "RESTRICT"


async def test_admin_can_create_and_update_reason(blocking_reasons_client):
    client, repository = blocking_reasons_client

    create_response = await client.post(
        "/api/v1/blocking-reasons",
        headers=auth(admin=True),
        json={
            "code": "NEW_REASON",
            "title": "New reason",
            "description": "Initial",
            "hard_block": False,
        },
    )
    reason_id = create_response.json()["id"]
    update_response = await client.patch(
        f"/api/v1/blocking-reasons/{reason_id}",
        headers=auth(admin=True),
        json={"title": "Updated reason", "is_active": False},
    )

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated reason"
    assert update_response.json()["is_active"] is False
    assert UUID(reason_id) in repository.reasons
