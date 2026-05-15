from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.dingtalk_card import parse_card_action_id
from app.schemas import TDLCardCallbackSubmission, TDLDraftUpdate
from app.services.tdl_service import (
    complete_tdl,
    confirm_tdl,
    postpone_tdl,
    request_help_tdl,
    snooze_tdl,
    update_draft_tdl,
)


@dataclass(frozen=True)
class CardCallbackResult:
    handled: bool
    action: str | None = None
    tdl_id: str | None = None
    status: str | None = None
    next_action: str | None = None
    required_fields: list[str] | None = None


ONE_CLICK_ACTIONS = {
    "confirm": confirm_tdl,
    "complete": complete_tdl,
    "need_help": request_help_tdl,
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


async def _submit_set_due_at(
    session: AsyncSession,
    *,
    tdl_id,
    actor_id: str,
    submission: TDLCardCallbackSubmission,
):
    if submission.due_at is None:
        return None
    return await update_draft_tdl(
        session,
        tdl_id,
        TDLDraftUpdate(due_at=submission.due_at),
        actor_id,
    )


async def _submit_postpone(
    session: AsyncSession,
    *,
    tdl_id,
    actor_id: str,
    submission: TDLCardCallbackSubmission,
):
    if submission.due_at is None:
        return None
    return await postpone_tdl(
        session,
        tdl_id,
        due_at=submission.due_at,
        actor_id=actor_id,
    )


async def _submit_snooze(
    session: AsyncSession,
    *,
    tdl_id,
    actor_id: str,
    submission: TDLCardCallbackSubmission,
):
    if submission.snooze_until is None:
        return None
    return await snooze_tdl(
        session,
        tdl_id,
        snooze_until=submission.snooze_until,
        actor_id=actor_id,
    )


FOLLOW_UP_SUBMITTERS = {
    "set_due_at": _submit_set_due_at,
    "postpone": _submit_postpone,
    "snooze": _submit_snooze,
}


async def handle_tdl_card_callback(
    session: AsyncSession,
    *,
    action_id: str,
    actor_id: str,
    submitted_fields: dict | None = None,
) -> CardCallbackResult:
    parsed = parse_card_action_id(action_id)
    if parsed is None:
        return CardCallbackResult(handled=False)
    action, tdl_id = parsed
    handler = ONE_CLICK_ACTIONS.get(action)
    if handler is None:
        follow_up = FOLLOW_UP_ACTIONS.get(action)
        if follow_up is None:
            return CardCallbackResult(handled=False, action=action, tdl_id=str(tdl_id))
        try:
            submission = TDLCardCallbackSubmission.model_validate(submitted_fields or {})
        except ValidationError:
            submission = TDLCardCallbackSubmission()
        submitter = FOLLOW_UP_SUBMITTERS.get(action)
        if submitter is not None:
            tdl = await submitter(
                session,
                tdl_id=tdl_id,
                actor_id=actor_id,
                submission=submission,
            )
            if tdl is not None:
                return CardCallbackResult(
                    handled=True,
                    action=action,
                    tdl_id=str(tdl.tdl_id),
                    status=tdl.status,
                )
        next_action, required_fields = follow_up
        return CardCallbackResult(
            handled=False,
            action=action,
            tdl_id=str(tdl_id),
            next_action=next_action,
            required_fields=required_fields,
        )

    tdl = await handler(session, tdl_id, actor_id)
    return CardCallbackResult(
        handled=True,
        action=action,
        tdl_id=str(tdl.tdl_id),
        status=tdl.status,
    )