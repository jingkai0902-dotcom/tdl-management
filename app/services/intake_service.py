from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.dingtalk_card import TDLCard, build_draft_card
from app.schemas import DingTalkIncomingMessage, TDLDraftCreate
from app.services.tdl_service import create_draft_tdl


def _fallback_due_at() -> datetime:
    return datetime.now(tz=UTC) + timedelta(days=1)


async def intake_dingtalk_message(
    session: AsyncSession,
    message: DingTalkIncomingMessage,
) -> TDLCard:
    payload = TDLDraftCreate(
        title=message.content.strip(),
        owner_id=message.sender_id,
        due_at=_fallback_due_at(),
        created_by=message.sender_id,
        source="dingtalk_msg",
        raw_text=message.content,
        confidence=0.0,
    )
    tdl = await create_draft_tdl(session, payload)
    return build_draft_card(tdl)
