from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import TDL
from app.integrations.dingtalk_client import DingTalkAPIError
from app.schemas import BatchConfirmDraftsRead, TDLRead
from app.services.calendar_service import (
    confirm_ready_drafts_with_calendar,
    confirm_tdl_with_calendar,
    create_calendar_event_for_tdl,
    create_tdl_with_calendar,
    should_create_calendar_event,
    sync_calendar_event_best_effort,
)


class FakeSession:
    def __init__(self, *tdls: TDL) -> None:
        self.items = []
        self.tdls = {tdl.tdl_id: tdl for tdl in tdls}

    def add(self, item) -> None:
        self.items.append(item)

    async def commit(self) -> None:
        return None

    async def refresh(self, item) -> None:
        return None

    async def get(self, model, identifier):
        return self.tdls.get(identifier)


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


@pytest.mark.asyncio
async def test_create_tdl_with_calendar_syncs_new_active_tdl(monkeypatch) -> None:
    tdl = _active_tdl()

    async def fake_create_tdl(session, payload):
        assert payload.title == "完成招生方案"
        return tdl

    async def fake_create_calendar_event_for_tdl(session, incoming_tdl, *, actor_id, client):
        assert incoming_tdl == tdl
        assert actor_id == "creator-1"
        assert client == "client"
        return incoming_tdl

    monkeypatch.setattr("app.services.calendar_service.create_tdl", fake_create_tdl)
    monkeypatch.setattr(
        "app.services.calendar_service.create_calendar_event_for_tdl",
        fake_create_calendar_event_for_tdl,
    )

    result = await create_tdl_with_calendar(
        "session",
        SimpleNamespace(title="完成招生方案", created_by="creator-1"),
        client="client",
    )

    assert result == tdl


@pytest.mark.asyncio
async def test_confirm_tdl_with_calendar_syncs_activated_draft(monkeypatch) -> None:
    tdl = _active_tdl()

    async def fake_confirm_tdl(session, incoming_tdl_id, actor_id):
        assert incoming_tdl_id == tdl.tdl_id
        assert actor_id == "actor-1"
        return tdl

    async def fake_create_calendar_event_for_tdl(session, incoming_tdl, *, actor_id, client):
        assert incoming_tdl == tdl
        assert actor_id == "actor-1"
        assert client == "client"
        return incoming_tdl

    monkeypatch.setattr("app.services.calendar_service.confirm_tdl", fake_confirm_tdl)
    monkeypatch.setattr(
        "app.services.calendar_service.create_calendar_event_for_tdl",
        fake_create_calendar_event_for_tdl,
    )

    result = await confirm_tdl_with_calendar(
        "session",
        tdl.tdl_id,
        "actor-1",
        client="client",
    )

    assert result == tdl


@pytest.mark.asyncio
async def test_sync_calendar_event_best_effort_keeps_tdl_when_dingtalk_fails(monkeypatch) -> None:
    tdl = _active_tdl()
    session = FakeSession()

    async def fake_create_calendar_event_for_tdl(*args, **kwargs):
        raise DingTalkAPIError("calendar unavailable")

    monkeypatch.setattr(
        "app.services.calendar_service.create_calendar_event_for_tdl",
        fake_create_calendar_event_for_tdl,
    )

    result = await sync_calendar_event_best_effort(
        session,
        tdl,
        actor_id="actor-1",
        client="client",
    )

    assert result == tdl
    assert session.items[-1].action == "calendar_create_failed"


@pytest.mark.asyncio
async def test_confirm_ready_drafts_with_calendar_syncs_confirmed_items(monkeypatch) -> None:
    tdl = _active_tdl()
    session = FakeSession(tdl)

    async def fake_confirm_ready_drafts(session, tdl_ids, actor_id):
        assert tdl_ids == [tdl.tdl_id]
        assert actor_id == "actor-1"
        return BatchConfirmDraftsRead(
            confirmed=[
                TDLRead(
                    tdl_id=tdl.tdl_id,
                    title=tdl.title,
                    owner_id=tdl.owner_id,
                    due_at=tdl.due_at,
                    status="active",
                    priority=tdl.priority,
                    source=tdl.source,
                )
            ],
            skipped=[],
        )

    synced = []

    async def fake_sync_calendar_event_best_effort(session, incoming_tdl, *, actor_id, client):
        synced.append((incoming_tdl, actor_id, client))
        return incoming_tdl

    monkeypatch.setattr(
        "app.services.calendar_service.confirm_ready_drafts",
        fake_confirm_ready_drafts,
    )
    monkeypatch.setattr(
        "app.services.calendar_service.sync_calendar_event_best_effort",
        fake_sync_calendar_event_best_effort,
    )

    result = await confirm_ready_drafts_with_calendar(
        session,
        [tdl.tdl_id],
        "actor-1",
        client="client",
    )

    assert [item.tdl_id for item in result.confirmed] == [tdl.tdl_id]
    assert synced == [(tdl, "actor-1", "client")]