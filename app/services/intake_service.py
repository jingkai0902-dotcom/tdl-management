from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.ai_client import AIClient, TDLExtractionError, TDLFieldDraft, get_ai_client
from app.integrations.dingtalk_card import TDLCard, build_created_card, build_draft_card
from app.schemas import DingTalkIncomingMessage, TDLCreate, TDLDraftCreate
from app.services.calendar_service import create_tdl_with_calendar
from app.services.tdl_service import create_draft_tdl


def _auto_create_rules() -> dict:
    return load_yaml_config("tdl_rules.yaml").get("auto_create", {})


async def intake_dingtalk_message(
    session: AsyncSession,
    message: DingTalkIncomingMessage,
    ai_client: AIClient | None = None,
) -> TDLCard:
    client = ai_client or get_ai_client()
    try:
        extracted = await client.extract_tdl_fields(message.content)
    except TDLExtractionError:
        extracted = TDLFieldDraft(
            title=message.content.strip()[:500],
            owner_id=None,
            due_at=None,
            confidence=0.0,
        )
    owner_id = extracted.owner_id or message.sender_id
    payload = TDLDraftCreate(
        title=extracted.title,
        owner_id=owner_id,
        due_at=extracted.due_at,
        created_by=message.sender_id,
        source="dingtalk_msg",
        raw_text=message.content,
        confidence=extracted.confidence,
    )

    rules = _auto_create_rules()
    minimum_confidence = float(rules.get("minimum_confidence", 0.85))
    require_due_at = bool(rules.get("require_due_at", True))
    allow_if_involves_others = bool(rules.get("allow_if_involves_others", False))
    can_auto_create = (
        (allow_if_involves_others or owner_id == message.sender_id)
        and (not require_due_at or extracted.due_at is not None)
        and extracted.confidence >= minimum_confidence
    )
    if can_auto_create:
        create_payload = TDLCreate(
            title=payload.title,
            owner_id=payload.owner_id,
            due_at=payload.due_at,
            created_by=payload.created_by,
            participants=payload.participants,
            priority=payload.priority,
            source=payload.source,
        )
        tdl = await create_tdl_with_calendar(session, create_payload)
        return build_created_card(tdl)

    tdl = await create_draft_tdl(session, payload)
    return build_draft_card(tdl)