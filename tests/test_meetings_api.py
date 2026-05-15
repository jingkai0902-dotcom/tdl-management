from types import SimpleNamespace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fastapi import HTTPException

from app.api.meetings import get_meeting_results_endpoint, parse_meeting_minutes_endpoint
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
            completion_criteria="形成正式 SOP",
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
    assert result.ready_to_confirm_count == 0
    assert result.incomplete_count == 1
    assert result.ready_to_confirm_tdls == []
    assert result.incomplete_tdls[0].tdl_id == tdl_id
    assert result.decisions[0].decision_id == decision_id
    assert result.tdls[0].tdl_id == tdl_id
    assert result.tdls[0].completion_criteria == "形成正式 SOP"
    assert result.tdls[0].missing_fields == ["due_at"]
    assert result.tdls[0].recommended_fields == []
    assert result.tdls[0].recommended_actions == []
    assert result.tdls[0].next_actions == ["set_due_at"]
    assert result.draft_cards[0].title == "TDL 草稿"
    assert [button.action for button in result.draft_cards[0].buttons] == ["set_due_at", "cancel"]


@pytest.mark.asyncio
async def test_parse_meeting_minutes_endpoint_groups_ready_and_incomplete_tdls(monkeypatch) -> None:
    meeting_id = uuid4()

    async def fake_parse_meeting_minutes(session, payload):
        meeting = SimpleNamespace(meeting_id=meeting_id)
        complete_tdl = SimpleNamespace(
            tdl_id=uuid4(),
            title="完成市场 SOP",
            owner_id="0962151633-1819579479",
            due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
            status="draft",
            priority="P2",
            source="meeting_minutes",
            completion_criteria="形成正式 SOP",
        )
        incomplete_tdl = SimpleNamespace(
            tdl_id=uuid4(),
            title="排定新师培训课表",
            owner_id=None,
            due_at=None,
            status="draft",
            priority="P2",
            source="meeting_minutes",
            completion_criteria=None,
        )
        return meeting, [], [complete_tdl, incomplete_tdl]

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

    assert result.ready_to_confirm_count == 1
    assert result.incomplete_count == 1
    assert len(result.ready_to_confirm_tdls) == 1
    assert len(result.incomplete_tdls) == 1
    assert result.ready_to_confirm_tdls[0].next_actions == ["confirm"]
    assert result.incomplete_tdls[0].next_actions == ["set_owner", "set_due_at"]
    assert result.incomplete_tdls[0].recommended_fields == ["completion_criteria"]
    assert result.incomplete_tdls[0].recommended_actions == ["set_completion_criteria"]


@pytest.mark.asyncio
async def test_get_meeting_results_endpoint_reuses_parse_shape(monkeypatch) -> None:
    meeting_id = uuid4()
    tdl_id = uuid4()

    async def fake_get_meeting_results(session, incoming_meeting_id):
        assert incoming_meeting_id == meeting_id
        meeting = SimpleNamespace(meeting_id=meeting_id)
        tdl = SimpleNamespace(
            tdl_id=tdl_id,
            title="完成市场 SOP",
            owner_id="0962151633-1819579479",
            due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
            status="draft",
            priority="P2",
            source="meeting_minutes",
            completion_criteria="形成正式 SOP",
        )
        return meeting, [], [tdl]

    monkeypatch.setattr("app.api.meetings.get_meeting_results", fake_get_meeting_results)

    result = await get_meeting_results_endpoint(meeting_id, session=None)

    assert result.meeting_id == meeting_id
    assert result.ready_to_confirm_count == 1
    assert result.ready_to_confirm_tdls[0].tdl_id == tdl_id


@pytest.mark.asyncio
async def test_get_meeting_results_endpoint_returns_404_for_missing_meeting(monkeypatch) -> None:
    async def fake_get_meeting_results(session, meeting_id):
        raise ValueError("Meeting not found")

    monkeypatch.setattr("app.api.meetings.get_meeting_results", fake_get_meeting_results)

    with pytest.raises(HTTPException) as exc:
        await get_meeting_results_endpoint(uuid4(), session=None)

    assert exc.value.status_code == 404
