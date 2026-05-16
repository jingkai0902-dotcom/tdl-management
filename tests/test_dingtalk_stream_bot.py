from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.dingtalk_card import build_card_action_id
from app.integrations.dingtalk_stream_bot import TDLCardCallbackHandler, TDLChatbotHandler
from app.services.dingtalk_card_callback_service import CardCallbackResult


class FakeSessionContext:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_chatbot_handler_replies_to_unsupported_message_types(monkeypatch) -> None:
    replies = []

    async def fake_intake(*args, **kwargs):
        raise AssertionError("unsupported messages must not enter intake")

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_text",
        lambda self, text, message: replies.append((text, message.message_type)),
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "audio",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert replies == [("当前先支持文字录入，语音和图片会在后续版本接入。", "audio")]


@pytest.mark.asyncio
async def test_chatbot_handler_accepts_rich_text_as_text(monkeypatch) -> None:
    seen = {}

    async def fake_intake(session, payload):
        seen["content"] = payload.content
        return SimpleNamespace()

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_markdown",
        lambda card: "rendered",
    )
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_text",
        lambda self, text, message: seen.setdefault("reply", text),
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "richText",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "content": {
                    "richText": [
                        {"text": "今天整理活动复盘"},
                        {"text": "完成标准是列出三条结论"},
                    ]
                },
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert seen == {
        "content": "今天整理活动复盘\n完成标准是列出三条结论",
        "reply": "rendered",
    }


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
