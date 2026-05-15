from uuid import uuid4
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.integrations.ai_client import DecisionDraft
from app.models import Decision, Meeting, TDL
from app.schemas import MeetingMinutesIngest
from app.services.meeting_service import get_meeting_results, parse_meeting_minutes


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

    async def get(self, model, identifier):
        for item in self.items:
            if model is Meeting and getattr(item, "meeting_id", None) == identifier:
                return item
            if model is TDL and getattr(item, "tdl_id", None) == identifier:
                return item
        return None

    async def execute(self, statement):
        model_name = statement.column_descriptions[0]["entity"].__name__
        if model_name == "Decision":
            rows = [item for item in self.items if isinstance(item, Decision)]
        else:
            rows = [item for item in self.items if isinstance(item, TDL)]
        return FakeResult(rows)


class FakeResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


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


class RealisticLibuAIClient:
    async def extract_meeting_decisions(self, source_text: str):
        assert "市场全链路 SOP" in source_text
        return [
            DecisionDraft(
                title="梳理前后端数据需求并形成统一入口",
                owner_id="0617564550-1513038363",
                completion_criteria="完成表格逻辑并支持从钉钉入口上传",
                tdl_title="梳理前后端数据需求并完成表格逻辑",
                due_at=None,
            ),
            DecisionDraft(
                title="排定新师培训课表",
                owner_id=None,
                completion_criteria="形成可执行课表",
                tdl_title="排定新师培训课表",
                due_at=None,
            ),
            DecisionDraft(
                title="完成市场全链路 SOP",
                owner_id="0962151633-1819579479",
                completion_criteria="形成跨部门 SOP 并纳入教学交付标准",
                tdl_title="完成市场全链路 SOP",
                due_at=datetime(2026, 5, 31, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            ),
        ]


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


@pytest.mark.asyncio
async def test_parse_realistic_libu_excerpt_creates_multiple_linked_drafts() -> None:
    source_text = Path("tests/fixtures/libu_may_meeting_excerpt.txt").read_text()
    session = FakeSession()
    payload = MeetingMinutesIngest(
        title="励步 5 月月会",
        source_text=source_text,
        created_by="0617564550-1513038363",
    )

    meeting, decisions, tdls = await parse_meeting_minutes(
        session,
        payload,
        RealisticLibuAIClient(),
    )

    assert meeting.title == "励步 5 月月会"
    assert len(decisions) == 3
    assert len(tdls) == 3
    assert all(tdl.meeting_id == meeting.meeting_id for tdl in tdls)
    assert all(tdl.status == "draft" for tdl in tdls)
    assert {tdl.owner_id for tdl in tdls} == {
        None,
        "0617564550-1513038363",
        "0962151633-1819579479",
    }
    assert [tdl.due_at for tdl in tdls].count(None) == 2
    assert tdls[2].due_at is not None


@pytest.mark.asyncio
async def test_get_meeting_results_returns_existing_meeting_artifacts() -> None:
    session = FakeSession()
    meeting = Meeting(title="励步 5 月月会", participants=[])
    session.add(meeting)
    await session.flush()
    decision = Decision(
        meeting_id=meeting.meeting_id,
        title="完成市场 SOP",
        owner_id="0962151633-1819579479",
    )
    session.add(decision)
    await session.flush()
    tdl = TDL(
        meeting_id=meeting.meeting_id,
        decision_id=decision.decision_id,
        title="完成市场 SOP",
        owner_id="0962151633-1819579479",
        due_at=None,
        created_by="0617564550-1513038363",
        source="meeting_minutes",
        status="draft",
    )
    session.add(tdl)
    await session.flush()

    found_meeting, decisions, tdls = await get_meeting_results(session, meeting.meeting_id)

    assert found_meeting.meeting_id == meeting.meeting_id
    assert decisions[0].decision_id == decision.decision_id
    assert tdls[0].tdl_id == tdl.tdl_id
