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
    completion_criteria: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    recommended_fields: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)

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
                "completion_criteria": tdl.completion_criteria,
                "missing_fields": [
                    field_name
                    for field_name in ("owner_id", "due_at")
                    if getattr(tdl, field_name) is None
                ],
                "recommended_fields": [
                    field_name
                    for field_name in ("completion_criteria",)
                    if getattr(tdl, field_name) is None
                ],
                "next_actions": cls._next_actions_for_tdl(tdl),
                "recommended_actions": cls._recommended_actions_for_tdl(tdl),
            }
        )

    @staticmethod
    def _next_actions_for_tdl(tdl) -> list[str]:
        actions = []
        if getattr(tdl, "owner_id") is None:
            actions.append("set_owner")
        if getattr(tdl, "due_at") is None:
            actions.append("set_due_at")
        if not actions:
            actions.append("confirm")
        return actions

    @staticmethod
    def _recommended_actions_for_tdl(tdl) -> list[str]:
        if getattr(tdl, "completion_criteria") is None:
            return ["set_completion_criteria"]
        return []


class DingTalkIncomingMessage(BaseModel):
    message_id: str
    sender_id: str
    sender_nick: str | None = None
    content: str = Field(min_length=1)


class DingTalkAction(BaseModel):
    action: str
    tdl_id: UUID
    actor_id: str


class TDLPostponeAction(BaseModel):
    tdl_id: UUID
    actor_id: str = Field(min_length=1, max_length=128)
    due_at: datetime


class TDLSnoozeAction(BaseModel):
    tdl_id: UUID
    actor_id: str = Field(min_length=1, max_length=128)
    snooze_until: datetime


class TDLDraftUpdate(BaseModel):
    owner_id: str | None = Field(default=None, min_length=1, max_length=128)
    due_at: datetime | None = None
    completion_criteria: str | None = None


class TDLCardTimeSubmission(BaseModel):
    """Time-based card callback submissions: set_due_at, postpone, snooze."""

    due_at: datetime | None = None
    snooze_until: datetime | None = None


class TDLCardOwnerSubmission(BaseModel):
    owner_id: str | None = Field(default=None, min_length=1, max_length=128)


class TDLCardCriteriaSubmission(BaseModel):
    completion_criteria: str | None = Field(default=None, min_length=1)


class BatchConfirmDraftsRequest(BaseModel):
    tdl_ids: list[UUID] = Field(min_length=1)
    actor_id: str = Field(min_length=1, max_length=128)


class BatchConfirmDraftsRead(BaseModel):
    confirmed: list[TDLRead]
    skipped: list[TDLRead]


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
    ready_to_confirm_tdls: list[TDLRead]
    incomplete_tdls: list[TDLRead]
    draft_cards: list[TDLCardRead]


class WeeklyReportStaleTDLRead(BaseModel):
    tdl_id: UUID
    title: str
    days_without_progress: int


class WeeklyReportRead(BaseModel):
    period_start: datetime
    period_end: datetime
    created_count: int
    completed_count: int
    overdue_open_count: int
    postponed_count: int
    waiting_count: int
    waiting_by_user: dict[str, int]
    blocked_count: int
    stale_tdls: list[WeeklyReportStaleTDLRead]
    due_next_week_count: int
    created_by_business_line: dict[str, int]


class ReminderCandidateRead(BaseModel):
    tdl_id: UUID
    owner_id: str
    title: str
    action: str
    overdue_days: int


class ReminderDispatchRead(BaseModel):
    owner_id: str
    action: str
    overdue_days: int
    card: TDLCardRead


class ReminderRunRead(BaseModel):
    candidate_count: int
    marked_attention_count: int
    dispatches: list[ReminderDispatchRead]