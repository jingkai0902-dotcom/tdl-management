from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.dingtalk_card import parse_card_action_id
from app.services.tdl_service import complete_tdl, confirm_tdl, request_help_tdl


@dataclass(frozen=True)
class CardCallbackResult:
    handled: bool
    action: str | None = None
    tdl_id: str | None = None
    status: str | None = None


async def handle_tdl_card_callback(
    session: AsyncSession,
    *,
    action_id: str,
    actor_id: str,
) -> CardCallbackResult:
    parsed = parse_card_action_id(action_id)
    if parsed is None:
        return CardCallbackResult(handled=False)
    action, tdl_id = parsed
    if action == "confirm":
        tdl = await confirm_tdl(session, tdl_id, actor_id)
    elif action == "complete":
        tdl = await complete_tdl(session, tdl_id, actor_id)
    elif action == "need_help":
        tdl = await request_help_tdl(session, tdl_id, actor_id)
    else:
        return CardCallbackResult(handled=False, action=action, tdl_id=str(tdl_id))
    return CardCallbackResult(
        handled=True,
        action=action,
        tdl_id=str(tdl.tdl_id),
        status=tdl.status,
    )
