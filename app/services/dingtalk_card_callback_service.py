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
    next_action: str | None = None
    required_fields: list[str] | None = None


ONE_CLICK_ACTIONS = {
    "confirm": "confirm_tdl",
    "complete": "complete_tdl",
    "need_help": "request_help_tdl",
}

FOLLOW_UP_ACTIONS = {
    "postpone": ("collect_due_at", ["due_at"]),
    "snooze": ("collect_snooze_until", ["snooze_until"]),
    "set_owner": ("collect_owner_id", ["owner_id"]),
    "set_due_at": ("collect_due_at", ["due_at"]),
    "set_completion_criteria": (
        "collect_completion_criteria",
        ["completion_criteria"],
    ),
}


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
    handler_name = ONE_CLICK_ACTIONS.get(action)
    if handler_name is None:
        follow_up = FOLLOW_UP_ACTIONS.get(action)
        if follow_up is None:
            return CardCallbackResult(handled=False, action=action, tdl_id=str(tdl_id))
        next_action, required_fields = follow_up
        return CardCallbackResult(
            handled=False,
            action=action,
            tdl_id=str(tdl_id),
            next_action=next_action,
            required_fields=required_fields,
        )

    handler = globals()[handler_name]
    tdl = await handler(session, tdl_id, actor_id)
    return CardCallbackResult(
        handled=True,
        action=action,
        tdl_id=str(tdl.tdl_id),
        status=tdl.status,
    )
