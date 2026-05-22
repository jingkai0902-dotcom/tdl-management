from __future__ import annotations

import logging

from app.config import get_settings
from app.database import SessionLocal
from app.integrations.ai_client import AIClient
from app.integrations.dingtalk_card import (
    render_interactive_card_data,
    render_markdown,
)
from app.integrations.dingtalk_client import DingTalkClient
from app.schemas import DingTalkIncomingMessage
from app.services.intake_queue_service import (
    claim_next_intake,
    mark_intake_done,
    mark_intake_failed,
)
from app.services.intake_service import intake_dingtalk_message


logger = logging.getLogger(__name__)


async def process_next_intake_queue_item(
    *,
    session_factory=SessionLocal,
    client_factory=DingTalkClient,
    ai_client: AIClient | None = None,
) -> bool:
    async with session_factory() as session:
        item = await claim_next_intake(session)
        if item is None:
            return False
        message = DingTalkIncomingMessage(
            message_id=item.message_id,
            sender_id=item.sender_id,
            sender_nick=item.sender_nick,
            content=item.content,
        )
        try:
            card = await intake_dingtalk_message(session, message, ai_client=ai_client)
            await _send_intake_card(item.sender_id, card, client_factory=client_factory)
            await mark_intake_done(session, item)
        except Exception as exc:
            await mark_intake_failed(session, item, error=exc)
            logger.exception(
                "intake_queue_item_failed intake_id=%s message_id=%s sender_id=%s",
                item.intake_id,
                item.message_id,
                item.sender_id,
            )
            raise
    return True


async def _send_intake_card(
    user_id: str,
    card,
    *,
    client_factory=DingTalkClient,
) -> None:
    settings = get_settings()
    client = client_factory()
    try:
        if settings.dingtalk_tdl_card_template_id and getattr(card, "buttons", None):
            await client.send_interactive_card_to_user(
                user_id=user_id,
                card_template_id=settings.dingtalk_tdl_card_template_id,
                card_data=render_interactive_card_data(card),
            )
            return
        await client.send_work_markdown(
            user_ids=[user_id],
            title=card.title,
            text=render_markdown(card, include_actions=False),
        )
    finally:
        await client.close()
