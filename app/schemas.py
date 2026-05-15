from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TDLCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    owner_id: str = Field(min_length=1, max_length=128)
    due_at: datetime
    created_by: str = Field(min_length=1, max_length=128)
    participants: list[str] = Field(default_factory=list)
    priority: str = "P2"
    source: str = "manual"


class TDLRead(BaseModel):
    tdl_id: UUID
    title: str
    owner_id: str
    due_at: datetime
    status: str
    priority: str
    source: str

    model_config = {"from_attributes": True}
