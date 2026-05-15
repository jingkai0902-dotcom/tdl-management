from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.dingtalk_card import build_card_action_id
from app.services.dingtalk_card_callback_service import (
    FOLLOW_UP_SUBMITTERS,
    ONE_CLICK_ACTIONS,
    handle_tdl_card_callback,
)


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_routes_complete(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_complete_tdl(session, incoming_tdl_id, actor_id):
        assert session == "session"
        assert incoming_tdl_id == tdl_id
        assert actor_id == "user-1"
        return SimpleNamespace(tdl_id=tdl_id, status="done")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "complete", fake_complete_tdl)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("complete", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "complete"
    assert result.tdl_id == str(tdl_id)
    assert result.status == "done"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_ignores_actions_needing_extra_input() -> None:
    tdl_id = uuid4()

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("postpone", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is False
    assert result.action == "postpone"
    assert result.tdl_id == str(tdl_id)
    assert result.next_action == "collect_due_at"
    assert result.required_fields == ["due_at"]


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_returns_owner_follow_up() -> None:
    tdl_id = uuid4()

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_owner", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is False
    assert result.action == "set_owner"
    assert result.next_action == "collect_owner_id"
    assert result.required_fields == ["owner_id"]


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_set_due_at(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.due_at.isoformat() == "2026-05-31T18:00:00+08:00"
        return SimpleNamespace(tdl_id=tdl_id, status="draft")

    monkeypatch.setitem(FOLLOW_UP_SUBMITTERS, "set_due_at", fake_submitter)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_due_at", tdl_id),
        actor_id="user-1",
        submitted_fields={"due_at": "2026-05-31T18:00:00+08:00"},
    )

    assert result.handled is True
    assert result.action == "set_due_at"
    assert result.tdl_id == str(tdl_id)
    assert result.status == "draft"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_postpone(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.due_at.isoformat() == "2026-06-02T18:00:00+08:00"
        return SimpleNamespace(tdl_id=tdl_id, status="active")

    monkeypatch.setitem(FOLLOW_UP_SUBMITTERS, "postpone", fake_submitter)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("postpone", tdl_id),
        actor_id="user-1",
        submitted_fields={"due_at": "2026-06-02T18:00:00+08:00"},
    )

    assert result.handled is True
    assert result.status == "active"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_snooze(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.snooze_until.isoformat() == "2026-05-20T09:00:00+08:00"
        return SimpleNamespace(tdl_id=tdl_id, status="snoozed")

    monkeypatch.setitem(FOLLOW_UP_SUBMITTERS, "snooze", fake_submitter)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("snooze", tdl_id),
        actor_id="user-1",
        submitted_fields={"snooze_until": "2026-05-20T09:00:00+08:00"},
    )

    assert result.handled is True
    assert result.status == "snoozed"