from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TicketKind(StrEnum):
    CREATE = "CREATE"
    EDIT = "EDIT"


class TicketStatus(StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


@dataclass(frozen=True, slots=True)
class BlockingReason:
    id: UUID
    title: str
    hard_block: bool
    code: str = ""
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class FieldReport:
    field_path: str
    message: str
    severity: str = "ERROR"


@dataclass(slots=True)
class ModerationTicket:
    id: UUID
    product_id: UUID
    seller_id: UUID
    kind: TicketKind
    status: TicketStatus
    queue_priority: int
    json_after: dict
    json_before: dict | None = None
    category_id: UUID | None = None
    assigned_moderator_id: UUID | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    decision_at: datetime | None = None
    decision_comment: str | None = None
    blocking_reason_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def has_skus(self) -> bool:
        skus = self.json_after.get("skus")
        return isinstance(skus, list) and len(skus) > 0

    def is_terminal(self) -> bool:
        return self.status == TicketStatus.HARD_BLOCKED
