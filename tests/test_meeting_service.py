from uuid import uuid4

import pytest

from app.integrations.ai_client import DecisionDraft
from app.schemas import MeetingMinutesIngest
from app.services.meeting_service import parse_meeting_minutes


class FakeSession:
    def __init__(self) -> None:
        self.items = []
        self.rollback_called = False

    def add(self, item) -> None:
        self.items.append(item)

    async def flush(self) -> None:
        for item in self.items:
            for attr in ("meeting_id", "decision_id", "tdl_id", "audit_id"):
                if hasattr(item, attr) and getattr(item, attr) is None:
                    setattr(item, attr, uuid4())

    async def commit(self) -> None:
        return None

    async def refresh(self, item) -> None:
        return None

    async def rollback(self) -> None:
        self.rollback_called = True


class FakeAIClient:
    async def extract_meeting_decisions(self, source_text: str):
        return [
            DecisionDraft(
                title="统一 6 月续费方案",
                owner_id="0962151633-1819579479",
                completion_criteria="提交最终方案",
                tdl_title="提交 6 月续费方案",
                due_at=None,
            )
        ]


class FailingAIClient:
    async def extract_meeting_decisions(self, source_text: str):
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_parse_meeting_minutes_creates_linked_draft_objects() -> None:
    session = FakeSession()
    payload = MeetingMinutesIngest(
        title="励步 5 月月会",
        source_text="统一 6 月续费方案",
        created_by="0617564550-1513038363",
    )

    meeting, decisions, tdls = await parse_meeting_minutes(session, payload, FakeAIClient())

    assert meeting.meeting_id is not None
    assert decisions[0].meeting_id == meeting.meeting_id
    assert tdls[0].meeting_id == meeting.meeting_id
    assert tdls[0].decision_id == decisions[0].decision_id
    assert tdls[0].status == "draft"
    assert tdls[0].due_at is None


@pytest.mark.asyncio
async def test_parse_meeting_minutes_rolls_back_when_extraction_fails() -> None:
    session = FakeSession()
    payload = MeetingMinutesIngest(
        title="励步 5 月月会",
        source_text="统一 6 月续费方案",
        created_by="0617564550-1513038363",
    )

    with pytest.raises(RuntimeError):
        await parse_meeting_minutes(session, payload, FailingAIClient())

    assert session.rollback_called is True
