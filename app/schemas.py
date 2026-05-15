from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TDLCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    owner_id: str = Field(min_length=1, max_length=128)
    due_at: datetime
    created_by: str = Field(min_length=1, max_length=128)
    participants: list[str] = Field(default_factory=list)
    priority: str = "P2"
    source: str = "manual"


class TDLDraftCreate(TDLCreate):
    due_at: datetime | None = None
    raw_text: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TDLRead(BaseModel):
    tdl_id: UUID
    title: str
    owner_id: str
    due_at: datetime | None
    status: str
    priority: str
    source: str

    model_config = {"from_attributes": True}


class DingTalkIncomingMessage(BaseModel):
    message_id: str
    sender_id: str
    sender_nick: str | None = None
    content: str = Field(min_length=1)


class DingTalkAction(BaseModel):
    action: str
    tdl_id: UUID
    actor_id: str


class MeetingMinutesIngest(BaseModel):
    title: str
    source_text: str
    created_by: str
