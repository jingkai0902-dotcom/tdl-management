import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.dingtalk_card import build_card_action_id
from app.integrations.dingtalk_stream_bot import (
    FEEDBACK_ENTRY_HINT,
    TDLCardCallbackHandler,
    TDLChatbotHandler,
    _append_feedback_entry_hint,
)
from app.services.dingtalk_card_callback_service import CardCallbackResult


class FakeSessionContext:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return None


def test_append_feedback_entry_hint_adds_r5_fallback() -> None:
    result = _append_feedback_entry_hint("已标记完成\n「招生方案」已完成，不再提醒")

    assert result.endswith(FEEDBACK_ENTRY_HINT)


def test_append_feedback_entry_hint_is_idempotent() -> None:
    text = f"已标记完成\n{FEEDBACK_ENTRY_HINT}"

    assert _append_feedback_entry_hint(text) == text


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
    assert replies == [("未能识别语音内容，请尝试用文字描述。", "audio")]


@pytest.mark.asyncio
async def test_chatbot_handler_accepts_audio_recognition_as_text(monkeypatch) -> None:
    seen = {}

    async def fake_intake(session, payload):
        seen["content"] = payload.content
        return SimpleNamespace(status="active", buttons=[])

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_standard_card_data",
        lambda card, **kwargs: {"card": "rendered"},
    )
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_markdown",
        lambda card: "rendered",
    )
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_card",
        lambda self, card_data, message: seen.setdefault("reply_card", card_data) or "card-id",
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "audio",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "content": {"recognition": "明天下午 6 点前整理续费复盘"},
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert seen["content"] == "明天下午 6 点前整理续费复盘"
    assert seen["reply_card"] == {"card": "rendered"}


@pytest.mark.asyncio
async def test_chatbot_handler_logs_processing_metadata_without_message_content(
    monkeypatch,
    caplog,
) -> None:
    async def fake_intake(session, payload):
        return SimpleNamespace(title="已创建 TDL", body=["done"], status="active", buttons=[])

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_standard_card_data",
        lambda card, **kwargs: {"card": "rendered"},
    )
    monkeypatch.setattr(TDLChatbotHandler, "reply_card", lambda self, card, message: "ok")

    caplog.set_level(logging.INFO, logger="app.integrations.dingtalk_stream_bot")

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "text",
                "senderStaffId": "user-1",
                "msgId": "msg-telemetry",
                "text": {"content": "这是一条不应该进入日志的任务正文"},
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert "message_id=msg-telemetry" in caplog.text
    assert "sender_id=user-1" in caplog.text
    assert "path=intake" in caplog.text
    assert "elapsed_ms=" in caplog.text
    assert "不应该进入日志" not in caplog.text


@pytest.mark.asyncio
async def test_chatbot_handler_routes_text_action_before_intake(monkeypatch) -> None:
    seen = {}

    async def fake_handle_text_action_command(session, *, actor_id, source_text):
        seen["text_action"] = (session, actor_id, source_text)
        return SimpleNamespace(title="已标记完成", status="done", buttons=[])

    async def fake_intake(*args, **kwargs):
        raise AssertionError("text action commands must not enter intake")

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.handle_text_action_command",
        fake_handle_text_action_command,
    )
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_standard_card_data",
        lambda card, **kwargs: {"card": "rendered"},
    )
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_card",
        lambda self, card_data, message: seen.setdefault("reply_card", card_data) or "card-id",
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "text",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "text": {"content": "完成：整理续费复盘"},
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert seen["text_action"] == ("session", "user-1", "完成：整理续费复盘")
    assert seen["reply_card"] == {"card": "rendered"}


@pytest.mark.asyncio
async def test_chatbot_handler_enqueues_intake_when_async_intake_enabled(monkeypatch) -> None:
    seen = {}

    async def fake_handle_text_action_command(*args, **kwargs):
        return None

    async def fake_enqueue(session, payload):
        seen["enqueued"] = (session, payload.message_id, payload.sender_id, payload.content)
        return SimpleNamespace(created=True)

    async def fake_intake(*args, **kwargs):
        raise AssertionError("async intake must not run inline extraction")

    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.get_settings",
        lambda: SimpleNamespace(dingtalk_async_intake_enabled=True),
    )
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.handle_text_action_command",
        fake_handle_text_action_command,
    )
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.enqueue_intake_message", fake_enqueue)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_text",
        lambda self, text, message: seen.setdefault("reply_text", text),
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "text",
                "senderStaffId": "user-1",
                "msgId": "msg-async",
                "text": {"content": "下周三前审核暑期班方案"},
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert seen["enqueued"] == ("session", "msg-async", "user-1", "下周三前审核暑期班方案")
    assert seen["reply_text"] == "已收到，正在整理成 TDL 卡片。"


@pytest.mark.asyncio
async def test_chatbot_handler_prefers_template_card_for_actionable_cards(monkeypatch) -> None:
    seen = {}

    async def fake_intake(session, payload):
        return SimpleNamespace(
            title="TDL 草稿",
            status="draft",
            buttons=[SimpleNamespace(action="confirm", label="确认创建", tdl_id=uuid4())],
        )

    async def fake_send_template_card_response(user_id, card):
        seen["template"] = (user_id, card.title)
        return True

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot._send_template_card_response",
        fake_send_template_card_response,
    )
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_card",
        lambda self, card_data, message: seen.setdefault("reply_card", card_data),
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "text",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "text": {"content": "test"},
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert seen == {"template": ("user-1", "TDL 草稿")}


@pytest.mark.asyncio
async def test_chatbot_handler_accepts_rich_text_as_text(monkeypatch) -> None:
    seen = {}

    async def fake_intake(session, payload):
        seen["content"] = payload.content
        return SimpleNamespace(status="active", buttons=[])

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_markdown",
        lambda card: "rendered",
    )

    def fake_render_standard_card_data(card, **kwargs):
        seen["card_kwargs"] = kwargs
        return {"card": "rendered"}

    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_standard_card_data",
        fake_render_standard_card_data,
    )
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_card",
        lambda self, card_data, message: seen.setdefault("reply_card", card_data) or "card-id",
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
        "card_kwargs": {"include_actions": True, "extra_body_lines": []},
        "reply_card": {"card": "rendered"},
    }


@pytest.mark.asyncio
async def test_chatbot_handler_falls_back_to_markdown_when_card_send_fails(monkeypatch) -> None:
    seen = {}

    async def fake_intake(session, payload):
        return SimpleNamespace(title="TDL 草稿", status="active", buttons=[])

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_standard_card_data",
        lambda card, **kwargs: {"card": "rendered"},
    )
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_markdown",
        lambda card, **kwargs: "rendered markdown",
    )
    monkeypatch.setattr(TDLChatbotHandler, "reply_card", lambda self, card_data, message: "")
    monkeypatch.setattr(
        TDLChatbotHandler,
        "reply_markdown",
        lambda self, title, text, message: seen.setdefault("reply_markdown", (title, text)),
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "text",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "text": {"content": "今天整理活动复盘"},
            }
        )
    )

    assert code == 200
    assert payload == "OK"
    assert seen["reply_markdown"] == ("TDL 草稿", "rendered markdown")


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
async def test_card_callback_handler_reads_standard_card_action_ids(monkeypatch) -> None:
    tdl_id = uuid4()
    expected_action_id = build_card_action_id("confirm", tdl_id)

    async def fake_handle_tdl_card_callback(session, *, action_id, actor_id, submitted_fields):
        assert session == "session"
        assert action_id == expected_action_id
        assert actor_id == "user-1"
        assert submitted_fields == {}
        return CardCallbackResult(
            handled=True,
            action="confirm",
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
                "content": '{"cardPrivateData":{"actionIds":["' + expected_action_id + '"],"params":{}}}',
            }
        )
    )

    assert code == 200
    assert payload["handled"] is True
    assert payload["status"] == "active"


@pytest.mark.asyncio
async def test_card_callback_handler_cancels_draft(monkeypatch) -> None:
    tdl_id = uuid4()
    cancel_action_id = build_card_action_id("cancel", tdl_id)
    seen = {}

    async def fake_handle_tdl_card_callback(session, *, action_id, actor_id, submitted_fields):
        assert session == "session"
        assert action_id == cancel_action_id
        assert actor_id == "user-1"
        return CardCallbackResult(
            handled=True,
            action="cancel",
            tdl_id=str(tdl_id),
            status="canceled",
            response_text="已忽略草稿",
        )

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.handle_tdl_card_callback",
        fake_handle_tdl_card_callback,
    )

    async def fake_feedback(actor_id, text):
        seen["feedback"] = (actor_id, text)

    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot._send_card_action_feedback",
        fake_feedback,
    )

    code, payload = await TDLCardCallbackHandler().process(
        SimpleNamespace(
            data={
                "userId": "user-1",
                "outTrackId": "track-1",
                "content": '{"cardPrivateData":{"actionIds":["' + cancel_action_id + '"],"params":{}}}',
            }
        )
    )

    assert code == 200
    assert payload["handled"] is True
    assert payload["action"] == "cancel"
    assert payload["status"] == "canceled"
    assert seen["feedback"] == ("user-1", "已忽略草稿")


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


@pytest.mark.asyncio
async def test_card_callback_handler_sends_follow_up_prompt(monkeypatch) -> None:
    tdl_id = uuid4()
    postpone_action_id = build_card_action_id("postpone", tdl_id)
    seen = {}

    async def fake_handle_tdl_card_callback(session, *, action_id, actor_id, submitted_fields):
        assert session == "session"
        assert action_id == postpone_action_id
        assert actor_id == "user-1"
        return CardCallbackResult(
            handled=False,
            action="postpone",
            tdl_id=str(tdl_id),
            next_action="collect_due_at",
            required_fields=["due_at"],
            response_text="请回复新的截止时间，例如：延期到明天下午六点",
        )

    async def fake_feedback(actor_id, text):
        seen["feedback"] = (actor_id, text)

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.handle_tdl_card_callback",
        fake_handle_tdl_card_callback,
    )
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot._send_card_action_feedback",
        fake_feedback,
    )

    code, payload = await TDLCardCallbackHandler().process(
        SimpleNamespace(
            data={
                "userId": "user-1",
                "content": '{"cardPrivateData":{"params":{"actionId":"'
                + postpone_action_id
                + '"}}}',
            }
        )
    )

    assert code == 200
    assert payload["handled"] is False
    assert payload["nextAction"] == "collect_due_at"
    assert "cardData" not in payload
    assert seen["feedback"] == ("user-1", "请回复新的截止时间，例如：延期到明天下午六点")


@pytest.mark.asyncio
async def test_card_callback_handler_sends_permission_feedback(monkeypatch) -> None:
    tdl_id = uuid4()
    complete_action_id = build_card_action_id("complete", tdl_id)
    seen = {}

    async def fake_handle_tdl_card_callback(session, *, action_id, actor_id, submitted_fields):
        assert session == "session"
        assert action_id == complete_action_id
        assert actor_id == "other-user"
        return CardCallbackResult(
            handled=False,
            action="complete",
            tdl_id=str(tdl_id),
            response_text="这条任务当前不是分配给你的，不能直接操作。请先让负责人更正后再处理。",
        )

    async def fake_feedback(actor_id, text):
        seen["feedback"] = (actor_id, text)

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.handle_tdl_card_callback",
        fake_handle_tdl_card_callback,
    )
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot._send_card_action_feedback",
        fake_feedback,
    )

    code, payload = await TDLCardCallbackHandler().process(
        SimpleNamespace(
            data={
                "userId": "other-user",
                "content": '{"cardPrivateData":{"params":{"actionId":"'
                + complete_action_id
                + '"}}}',
            }
        )
    )

    assert code == 200
    assert payload["handled"] is False
    assert payload["action"] == "complete"
    assert seen["feedback"] == (
        "other-user",
        "这条任务当前不是分配给你的，不能直接操作。请先让负责人更正后再处理。",
    )


@pytest.mark.asyncio
async def test_chatbot_handler_shows_confirmation_hint_for_complete_draft(monkeypatch) -> None:
    seen = {}

    async def fake_intake(session, payload):
        return SimpleNamespace(
            title="TDL 草稿",
            body=["test body"],
            status="draft",
            buttons=[SimpleNamespace(action="confirm", label="确认创建", tdl_id=None)],
        )

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_standard_card_data",
        lambda card, **kwargs: seen.setdefault("card_kwargs", kwargs) or {"card": "rendered"},
    )
    monkeypatch.setattr(
        TDLChatbotHandler, "reply_card", lambda self, card_data, message: "ok"
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "text",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "text": {"content": "test"},
            }
        )
    )

    assert code == 200
    assert seen["card_kwargs"]["include_actions"] is True
    assert "确认创建" in seen["card_kwargs"]["extra_body_lines"][0]
    assert "忽略" in seen["card_kwargs"]["extra_body_lines"][0]


@pytest.mark.asyncio
async def test_chatbot_handler_shows_supplement_hint_for_incomplete_draft(monkeypatch) -> None:
    seen = {}

    async def fake_intake(session, payload):
        return SimpleNamespace(
            title="TDL 草稿",
            body=["test body"],
            status="draft",
            buttons=[SimpleNamespace(action="set_due_at", label="补截止时间", tdl_id=None)],
        )

    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.SessionLocal", FakeSessionContext)
    monkeypatch.setattr("app.integrations.dingtalk_stream_bot.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr(
        "app.integrations.dingtalk_stream_bot.render_standard_card_data",
        lambda card, **kwargs: seen.setdefault("card_kwargs", kwargs) or {"card": "rendered"},
    )
    monkeypatch.setattr(
        TDLChatbotHandler, "reply_card", lambda self, card_data, message: "ok"
    )

    code, payload = await TDLChatbotHandler().process(
        SimpleNamespace(
            data={
                "msgtype": "text",
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "text": {"content": "test"},
            }
        )
    )

    assert code == 200
    assert seen["card_kwargs"]["include_actions"] is True
    footer = seen["card_kwargs"]["extra_body_lines"][0]
    assert "补充缺失信息" in footer
    assert "忽略" in footer
