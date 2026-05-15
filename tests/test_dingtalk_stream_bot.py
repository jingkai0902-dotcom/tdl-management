from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.dingtalk_card import build_card_action_id
from app.integrations.dingtalk_stream_bot import TDLCardCallbackHandler
from app.services.dingtalk_card_callback_service import CardCallbackResult


class FakeSessionContext:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_card_callback_handler_routes_action(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_handle_tdl_card_callback(session, *, action_id, actor_id, submitted_fields):
        assert session == "session"
        assert action_id == build_card_action_id("complete", tdl_id)
        assert actor_id == "user-1"
        assert submitted_fields == {"actionId": build_card_action_id("complete", tdl_id)}
        return CardCallbackResult(
            handled=True,
            action="complete",
            tdl_id=str(tdl_id),
            status="done",
        )

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.handle_tdl_card_callback",
        fake_handle_tdl_card_callback,
    )

    code, payload = await TDLCardCallbackHandler().process(
        SimpleNamespace(
            data={
                "userId": "user-1",
                "content": '{"cardPrivateData":{"params":{"actionId":"'
                + build_card_action_id("complete", tdl_id)
                + '"}}}',
            }
        )
    )

    assert code == 200
    assert payload == {
        "handled": True,
        "action": "complete",
        "tdlId": str(tdl_id),
        "status": "done",
        "nextAction": None,
        "requiredFields": None,
    }


@pytest.mark.asyncio
async def test_card_callback_handler_passes_follow_up_fields(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_handle_tdl_card_callback(session, *, action_id, actor_id, submitted_fields):
        assert session == "session"
        assert action_id == build_card_action_id("postpone", tdl_id)
        assert actor_id == "user-1"
        assert submitted_fields["due_at"] == "2026-06-02T18:00:00+08:00"
        return CardCallbackResult(
            handled=True,
            action="postpone",
            tdl_id=str(tdl_id),
            status="active",
        )

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.handle_tdl_card_callback",
        fake_handle_tdl_card_callback,
    )

    code, payload = await TDLCardCallbackHandler().process(
        SimpleNamespace(
            data={
                "userId": "user-1",
                "content": '{"cardPrivateData":{"params":{"actionId":"'
                + build_card_action_id("postpone", tdl_id)
                + '","due_at":"2026-06-02T18:00:00+08:00"}}}',
            }
        )
    )

    assert code == 200
    assert payload["handled"] is True
    assert payload["action"] == "postpone"