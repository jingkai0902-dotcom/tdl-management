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
    owner_id: str | None = Field(default=None, min_length=1, max_length=128)
    due_at: datetime | None = None
    raw_text: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TDLRead(BaseModel):
    tdl_id: UUID
    title: str
    owner_id: str | None
    due_at: datetime | None
    status: str
    priority: str
    source: str
    missing_fields: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @classmethod
    def from_tdl(cls, tdl) -> "TDLRead":
        return cls.model_validate(
            {
                "tdl_id": tdl.tdl_id,
                "title": tdl.title,
                "owner_id": tdl.owner_id,
                "due_at": tdl.due_at,
                "status": tdl.status,
                "priority": tdl.priority,
                "source": tdl.source,
                "missing_fields": [
                    field_name
                    for field_name in ("owner_id", "due_at")
                    if getattr(tdl, field_name) is None
                ],
            }
        )


class DingTalkIncomingMessage(BaseModel):
    message_id: str
    sender_id: str
    sender_nick: str | None = None
    content: str = Field(min_length=1)


class DingTalkAction(BaseModel):
    action: str
    tdl_id: UUID
    actor_id: str


class TDLDraftUpdate(BaseModel):
    owner_id: str | None = Field(default=None, min_length=1, max_length=128)
    due_at: datetime | None = None


class CardButtonRead(BaseModel):
    label: str
    action: str
    tdl_id: UUID

    model_config = {"from_attributes": True}


class TDLCardRead(BaseModel):
    title: str
    body: list[str]
    buttons: list[CardButtonRead]
    status: str

    model_config = {"from_attributes": True}


class MeetingMinutesIngest(BaseModel):
    title: str
    source_text: str
    created_by: str


class DecisionRead(BaseModel):
    decision_id: UUID
    title: str
    owner_id: str | None
    completion_criteria: str | None

    model_config = {"from_attributes": True}


class MeetingParseRead(BaseModel):
    meeting_id: UUID
    decision_count: int
    tdl_count: int
    ready_to_confirm_count: int
    incomplete_count: int
    decisions: list[DecisionRead]
    tdls: list[TDLRead]
    draft_cards: list[TDLCardRead]
