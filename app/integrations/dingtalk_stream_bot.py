from __future__ import annotations

import asyncio
import logging

import dingtalk_stream
from dingtalk_stream import AckMessage, CallbackHandler, CardCallbackMessage
from dingtalk_stream.chatbot import ChatbotHandler, ChatbotMessage

from app.config import get_settings
from app.database import SessionLocal
from app.integrations.dingtalk_card import render_markdown
from app.schemas import DingTalkIncomingMessage
from app.services.dingtalk_card_callback_service import handle_tdl_card_callback
from app.services.intake_service import intake_dingtalk_message


logger = logging.getLogger(__name__)


class TDLChatbotHandler(ChatbotHandler):
    async def process(self, callback):
        incoming = callback.data
        message = ChatbotMessage.from_dict(incoming) if isinstance(incoming, dict) else incoming
        content = getattr(getattr(message, "text", None), "content", "") or ""
        sender_id = getattr(message, "sender_staff_id", "") or getattr(message, "sender_id", "")
        if not content or not sender_id:
            return AckMessage.STATUS_OK, "OK"

        payload = DingTalkIncomingMessage(
            message_id=getattr(message, "msg_id", "") or getattr(message, "conversation_id", ""),
            sender_id=sender_id,
            sender_nick=getattr(message, "sender_nick", None),
            content=content.strip(),
        )
        async with SessionLocal() as session:
            card = await intake_dingtalk_message(session, payload)
        self.reply_text(render_markdown(card), message)
        return AckMessage.STATUS_OK, "OK"


class TDLCardCallbackHandler(CallbackHandler):
    async def process(self, callback):
        incoming = CardCallbackMessage.from_dict(callback.data)
        card_private_data = incoming.content.get("cardPrivateData", {})
        params = card_private_data.get("params", {})
        action_id = params.get("actionId") or params.get("action_id") or params.get("action")
        actor_id = incoming.user_id
        if not action_id or not actor_id:
            return AckMessage.STATUS_BAD_REQUEST, {"handled": False}

        async with SessionLocal() as session:
            result = await handle_tdl_card_callback(
                session,
                action_id=action_id,
                actor_id=actor_id,
                submitted_fields=params,
            )
        return AckMessage.STATUS_OK, {
            "handled": result.handled,
            "action": result.action,
            "tdlId": result.tdl_id,
            "status": result.status,
            "nextAction": result.next_action,
            "requiredFields": result.required_fields,
        }


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