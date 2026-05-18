from __future__ import annotations

import asyncio
import logging

import dingtalk_stream
from dingtalk_stream import AckMessage, CallbackHandler, CardCallbackMessage
from dingtalk_stream.frames import Headers
from dingtalk_stream.chatbot import ChatbotHandler, ChatbotMessage

from app.config import get_settings
from app.database import SessionLocal
from app.integrations.dingtalk_card import render_markdown, render_standard_card_data
from app.schemas import DingTalkIncomingMessage
from app.services.dingtalk_card_callback_service import handle_tdl_card_callback
from app.services.intake_service import intake_dingtalk_message
from app.services.text_action_service import handle_text_action_command


logger = logging.getLogger(__name__)


def _extract_message_content(message: ChatbotMessage) -> str:
    if message.message_type == "text":
        return getattr(getattr(message, "text", None), "content", "") or ""
    if message.message_type == "richText":
        return "\n".join(message.get_text_list() or [])
    return ""


def _chatbot_card_footer_lines(card) -> list[str]:
    if card.status != "draft":
        return []
    has_confirm = any(button.action == "confirm" for button in card.buttons)
    if has_confirm:
        return ["可直接回复“确认创建”激活，或回复“忽略”取消。"]
    return ["可直接回复补充缺失信息，或回复“忽略”取消。"]


class TDLChatbotHandler(ChatbotHandler):
    async def process(self, callback):
        incoming = callback.data
        message = ChatbotMessage.from_dict(incoming) if isinstance(incoming, dict) else incoming
        content = _extract_message_content(message)
        # 语音消息：钉钉已自带语音识别，直接从 recognition 字段取文字
        if not content and isinstance(incoming, dict) and incoming.get("msgtype") == "audio":
            content = (incoming.get("content", {}) or {}).get("recognition", "")
        sender_id = getattr(message, "sender_staff_id", "") or getattr(message, "sender_id", "")
        if not sender_id:
            return AckMessage.STATUS_OK, "OK"
        if not content:
            self.reply_text("未能识别语音内容，请尝试用文字描述。", message)
            return AckMessage.STATUS_OK, "OK"

        payload = DingTalkIncomingMessage(
            message_id=getattr(message, "message_id", "") or getattr(message, "conversation_id", ""),
            sender_id=sender_id,
            sender_nick=getattr(message, "sender_nick", None),
            content=content.strip(),
        )
        async with SessionLocal() as session:
            card = await handle_text_action_command(
                session,
                actor_id=payload.sender_id,
                source_text=payload.content,
            )
            if card is None:
                card = await intake_dingtalk_message(session, payload)
        card_data = render_standard_card_data(
            card,
            include_actions=False,
            extra_body_lines=_chatbot_card_footer_lines(card),
        )
        if not self.reply_card(card_data, message):
            self.reply_markdown(card.title, render_markdown(card, include_actions=False), message)
        return AckMessage.STATUS_OK, "OK"


class TDLCardCallbackHandler(CallbackHandler):
    async def process(self, callback):
        incoming = CardCallbackMessage.from_dict(callback.data)
        card_private_data = incoming.content.get("cardPrivateData", {})
        params = card_private_data.get("params", {})
        action_ids = card_private_data.get("actionIds") or []
        action_id = (
            params.get("actionId")
            or params.get("action_id")
            or params.get("action")
            or (action_ids[0] if action_ids else None)
        )
        actor_id = incoming.user_id
        if not action_id or not actor_id:
            logger.warning("Unusable DingTalk card callback content: %s", incoming.content)
            return AckMessage.STATUS_BAD_REQUEST, {"handled": False}

        async with SessionLocal() as session:
            result = await handle_tdl_card_callback(
                session,
                action_id=action_id,
                actor_id=actor_id,
                submitted_fields=params,
            )

        if result.handled and result.response_text:
            await _send_card_action_feedback(actor_id, result.response_text)

        return AckMessage.STATUS_OK, {
            "handled": result.handled,
            "action": result.action,
            "tdlId": result.tdl_id,
            "status": result.status,
            "nextAction": result.next_action,
            "requiredFields": result.required_fields,
        }

    async def raw_process(self, callback_message):
        """Override to include card update instructions for visual feedback."""
        code, message = await self.process(callback_message)
        ack_message = AckMessage()
        ack_message.code = code
        ack_message.headers.message_id = callback_message.headers.message_id
        ack_message.headers.content_type = Headers.CONTENT_TYPE_APPLICATION_JSON
        ack_message.data = {
            "response": message,
            "cardUpdateOptions": {"updateCardDataByKey": True},
        }
        return ack_message


async def _send_card_action_feedback(actor_id: str, text: str) -> None:
    """Send a work notification so the user sees immediate feedback after clicking a card button."""
    try:
        from app.integrations.dingtalk_client import DingTalkClient
        client = DingTalkClient()
        await client.send_work_markdown(
            user_ids=[actor_id],
            title="TDL",
            text=text,
        )
    except Exception:
        logger.exception("Failed to send card action feedback to user=%s", actor_id)


def run_stream_bot() -> None:
    settings = get_settings()
    credential = dingtalk_stream.Credential(
        settings.dingtalk_app_key,
        settings.dingtalk_app_secret,
    )
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
        TDLChatbotHandler(),
    )
    client.register_callback_handler(
        dingtalk_stream.CallbackHandler.TOPIC_CARD_CALLBACK,
        TDLCardCallbackHandler(),
    )
    client.start_forever()


if __name__ == "__main__":
    asyncio.run(asyncio.to_thread(run_stream_bot))
