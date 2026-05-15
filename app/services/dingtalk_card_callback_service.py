from dataclasses import dataclass
import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.dingtalk_card import parse_card_action_id
from app.schemas import (
    TDLCardCriteriaSubmission,
    TDLCardOwnerSubmission,
    TDLCardTimeSubmission,
    TDLDraftUpdate,
)
from app.services.tdl_service import (
    complete_tdl,
    postpone_tdl,
    request_help_tdl,
    snooze_tdl,
    update_draft_tdl,
)
from app.services.calendar_service import confirm_tdl_with_calendar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CardCallbackResult:
    handled: bool
    action: str | None = None
    tdl_id: str | None = None
    status: str | None = None
    next_action: str | None = None
    required_fields: list[str] | None = None


ONE_CLICK_ACTIONS = {
    "confirm": confirm_tdl_with_calendar,
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


def _management_owner_ids() -> set[str]:
    roster = load_yaml_config("management_roster.yaml")
    return {
        member["dingtalk_user_id"]
        for member in roster.get("management", [])
        if member.get("dingtalk_user_id")
    }


async def _submit_set_owner(
    session: AsyncSession,
    *,
    tdl_id,
    actor_id: str,
    submission: TDLCardOwnerSubmission,
):
    if submission.owner_id is None or submission.owner_id not in _management_owner_ids():
        return None
    return await update_draft_tdl(
        session,
        tdl_id,
        TDLDraftUpdate(owner_id=submission.owner_id),
        actor_id,
    )


async def _submit_set_due_at(
    session: AsyncSession,
    *,
    tdl_id,
    actor_id: str,
    submission: TDLCardTimeSubmission,
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
    submission: TDLCardTimeSubmission,
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
    submission: TDLCardTimeSubmission,
):
    if submission.snooze_until is None:
        return None
    return await snooze_tdl(
        session,
        tdl_id,
        snooze_until=submission.snooze_until,
        actor_id=actor_id,
    )


async def _submit_completion_criteria(
    session: AsyncSession,
    *,
    tdl_id,
    actor_id: str,
    submission: TDLCardCriteriaSubmission,
):
    if submission.completion_criteria is None:
        return None
    return await update_draft_tdl(
        session,
        tdl_id,
        TDLDraftUpdate(completion_criteria=submission.completion_criteria),
        actor_id,
    )


FOLLOW_UP_SUBMITTERS = {
    "set_owner": _submit_set_owner,
    "set_due_at": _submit_set_due_at,
    "postpone": _submit_postpone,
    "snooze": _submit_snooze,
    "set_completion_criteria": _submit_completion_criteria,
}

FOLLOW_UP_SUBMISSION_MODELS = {
    "set_owner": TDLCardOwnerSubmission,
    "set_due_at": TDLCardTimeSubmission,
    "postpone": TDLCardTimeSubmission,
    "snooze": TDLCardTimeSubmission,
    "set_completion_criteria": TDLCardCriteriaSubmission,
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
        submitter = FOLLOW_UP_SUBMITTERS.get(action)
        submission_model = FOLLOW_UP_SUBMISSION_MODELS.get(action)
        if submitter is not None and submission_model is not None:
            try:
                submission = submission_model.model_validate(submitted_fields or {})
            except ValidationError as exc:
                logger.debug("Card callback submission validation failed: %s", exc)
                submission = submission_model()
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