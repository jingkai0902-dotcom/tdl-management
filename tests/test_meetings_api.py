from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.meetings import parse_meeting_minutes_endpoint
from app.schemas import MeetingMinutesIngest


@pytest.mark.asyncio
async def test_parse_meeting_minutes_endpoint_returns_decision_and_tdl_details(monkeypatch) -> None:
    meeting_id = uuid4()
    decision_id = uuid4()
    tdl_id = uuid4()

    async def fake_parse_meeting_minutes(session, payload):
        meeting = SimpleNamespace(meeting_id=meeting_id)
        decision = SimpleNamespace(
            decision_id=decision_id,
            title="完成市场 SOP",
            owner_id="0962151633-1819579479",
            completion_criteria="形成正式 SOP",
        )
        tdl = SimpleNamespace(
            tdl_id=tdl_id,
            title="完成市场 SOP",
            owner_id="0962151633-1819579479",
            due_at=None,
            status="draft",
            priority="P2",
            source="meeting_minutes",
        )
        return meeting, [decision], [tdl]

    monkeypatch.setattr(
        "app.api.meetings.parse_meeting_minutes",
        fake_parse_meeting_minutes,
    )

    result = await parse_meeting_minutes_endpoint(
        MeetingMinutesIngest(
            title="励步 5 月月会",
            source_text="市场 SOP",
            created_by="0617564550-1513038363",
        ),
        session=None,
    )

    assert result.meeting_id == meeting_id
    assert result.decision_count == 1
    assert result.tdl_count == 1
    assert result.decisions[0].decision_id == decision_id
    assert result.tdls[0].tdl_id == tdl_id
    assert result.tdls[0].missing_fields == ["due_at"]
    assert result.draft_cards[0].title == "TDL 草稿"
    assert result.draft_cards[0].buttons[0].action == "confirm"
