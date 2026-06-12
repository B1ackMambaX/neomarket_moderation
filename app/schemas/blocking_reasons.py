from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BlockingReasonCreateRequest(BaseModel):
    code: str = Field(pattern=r"^[A-Z_]+$", max_length=64)
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    hard_block: bool


class BlockingReasonUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class BlockingReasonResponse(BaseModel):
    id: UUID
    code: str
    title: str
    description: str | None
    hard_block: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
