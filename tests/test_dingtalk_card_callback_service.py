from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.dingtalk_card import build_card_action_id
from app.services.dingtalk_card_callback_service import handle_tdl_card_callback


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_routes_complete(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_complete_tdl(session, incoming_tdl_id, actor_id):
        assert session == "session"
        assert incoming_tdl_id == tdl_id
        assert actor_id == "user-1"
        return SimpleNamespace(tdl_id=tdl_id, status="done")

    monkeypatch.setattr(
        "app.services.dingtalk_card_callback_service.complete_tdl",
        fake_complete_tdl,
    )

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
