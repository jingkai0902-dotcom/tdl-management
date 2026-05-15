from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import TDL
from app.services.calendar_service import (
    create_calendar_event_for_tdl,
    should_create_calendar_event,
)


class FakeSession:
    def __init__(self) -> None:
        self.items = []

    def add(self, item) -> None:
        self.items.append(item)

    async def commit(self) -> None:
        return None

    async def refresh(self, item) -> None:
        return None


def _active_tdl() -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title="完成招生方案",
        owner_id="owner-1",
        participants=["user-2"],
        due_at=datetime(2026, 5, 20, 18, 0, tzinfo=UTC),
        priority="P1",
        created_by="creator-1",
        source="manual",
        status="active",
    )


def test_should_create_calendar_event_only_accepts_active_complete_tdls() -> None:
    active = _active_tdl()
    draft = _active_tdl()
    draft.status = "draft"
    missing_due_at = _active_tdl()
    missing_due_at.due_at = None
    already_synced = _active_tdl()
    already_synced.calendar_event_id = "evt-1"

    assert should_create_calendar_event(active) is True
    assert should_create_calendar_event(draft) is False
    assert should_create_calendar_event(missing_due_at) is False
    assert should_create_calendar_event(already_synced) is False


@pytest.mark.asyncio
async def test_create_calendar_event_for_tdl_writes_event_id_and_audit() -> None:
    tdl = _active_tdl()
    session = FakeSession()

    class FakeDingTalkClient:
        async def create_tdl_calendar_event(self, **kwargs):
            assert kwargs == {
                "owner_id": "owner-1",
                "title": "完成招生方案",
                "due_at": datetime(2026, 5, 20, 18, 0, tzinfo=UTC),
                "participant_user_ids": ["user-2"],
                "description": f"TDL ID: {tdl.tdl_id}",
                "duration_minutes": 30,
            }
            return "evt-1"

    synced = await create_calendar_event_for_tdl(
        session,
        tdl,
        actor_id="system",
        client=FakeDingTalkClient(),
    )

    assert synced.calendar_event_id == "evt-1"
    assert session.items[-1].action == "calendar_create"
    assert session.items[-1].payload == {"calendar_event_id": "evt-1"}