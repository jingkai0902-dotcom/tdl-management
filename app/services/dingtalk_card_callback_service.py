from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.dingtalk_card import parse_card_action_id
from app.models import TDL
from app.schemas import (
    TDLCardCriteriaSubmission,
    TDLCardOwnerSubmission,
    TDLCardTimeSubmission,
    TDLDraftUpdate,
)
from app.services.tdl_service import (
    cancel_draft_tdl,
    complete_tdl,
    reject_tdl,
    request_help_tdl,
    snooze_tdl,
    update_draft_tdl,
)
from app.services.calendar_service import confirm_tdl_with_calendar, postpone_tdl_with_calendar

logger = logging.getLogger(__name__)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class CardCallbackResult:
    handled: bool
    action: str | None = None
    tdl_id: str | None = None
    status: str | None = None
    next_action: str | None = None
    required_fields: list[str] | None = None
    response_text: str | None = None


ONE_CLICK_ACTIONS = {
    "confirm": confirm_tdl_with_calendar,
    "complete": complete_tdl,
    "need_help": request_help_tdl,
    "reject": reject_tdl,
    "cancel": cancel_draft_tdl,
}

IDEMPOTENT_ACTION_STATUSES = {
    "confirm": {"active", "attention", "snoozed", "done"},
    "complete": {"done"},
    "need_help": {"attention"},
    "reject": {"rejected"},
    "cancel": {"canceled"},
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
    return await postpone_tdl_with_calendar(
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


def _default_snooze_until(now: datetime | None = None) -> datetime:
    resolved_now = now or datetime.now(tz=SHANGHAI_TZ)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=UTC)
    local_now = resolved_now.astimezone(SHANGHAI_TZ)
    tomorrow = local_now + timedelta(days=1)
    return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)


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
                resolved_fields = submitted_fields or {}
                if action == "snooze" and not resolved_fields.get("snooze_until"):
                    resolved_fields = {
                        **resolved_fields,
                        "snooze_until": _default_snooze_until(),
                    }
                submission = submission_model.model_validate(resolved_fields)
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
                    response_text=_follow_up_feedback(action, tdl, submission),
                )
        next_action, required_fields = follow_up
        return CardCallbackResult(
            handled=False,
            action=action,
            tdl_id=str(tdl_id),
            next_action=next_action,
            required_fields=required_fields,
            response_text=_follow_up_prompt(action),
        )

    try:
        tdl = await handler(session, tdl_id, actor_id)
    except ValueError as exc:
        if _is_owner_permission_error(exc):
            return CardCallbackResult(
                handled=False,
                action=action,
                tdl_id=str(tdl_id),
                response_text="这条任务当前不是分配给你的，不能直接操作。请先让负责人更正后再处理。",
            )
        existing = await _get_existing_tdl(session, tdl_id)
        if existing is None or existing.status not in IDEMPOTENT_ACTION_STATUSES.get(action, set()):
            raise
        return CardCallbackResult(
            handled=True,
            action=action,
            tdl_id=str(existing.tdl_id),
            status=existing.status,
            response_text=f"{_one_click_feedback(action, existing)}\n（已处理）",
        )
    return CardCallbackResult(
        handled=True,
        action=action,
        tdl_id=str(tdl.tdl_id),
        status=tdl.status,
        response_text=_one_click_feedback(action, tdl),
    )


def _feedback_title(tdl) -> str:
    title = getattr(tdl, "title", None)
    return f"「{title}」" if title else "这条 TDL"


def _one_click_feedback(action: str, tdl) -> str:
    title = _feedback_title(tdl)
    return {
        "confirm": f"TDL 已创建\n{title} 已进入待办",
        "complete": f"已标记完成\n{title} 已完成，不再提醒",
        "need_help": f"已标记为需要协助\n{title} 已进入需协助状态",
        "reject": f"已标记为不是我的任务\n{title} 已拒绝归属，不再提醒你",
        "cancel": f"已忽略草稿\n{title} 已取消，不再提醒",
    }.get(action, f"操作完成：{action}\n{title}")


def _follow_up_feedback(action: str, tdl, submission) -> str:
    title = _feedback_title(tdl)
    if action == "snooze":
        return _snooze_feedback(submission, title=title)
    return {
        "set_owner": f"负责人已更新\n{title}",
        "set_due_at": f"截止时间已更新\n{title}",
        "postpone": f"已延期\n{title}",
        "set_completion_criteria": f"完成标准已更新\n{title}",
    }.get(action, f"已更新：{action}\n{title}")


def _snooze_feedback(submission, *, title: str | None = None) -> str:
    snooze_until = getattr(submission, "snooze_until", None)
    prefix = "已暂缓" if title is None else f"已暂缓\n{title}"
    return (
        f"{prefix}\n"
        f"下次提醒：{snooze_until.astimezone(SHANGHAI_TZ):%Y-%m-%d %H:%M}"
        if snooze_until
        else prefix
    )


async def _get_existing_tdl(session: AsyncSession, tdl_id) -> TDL | None:
    getter = getattr(session, "get", None)
    if getter is None:
        return None
    return await getter(TDL, tdl_id)


def _is_owner_permission_error(exc: ValueError) -> bool:
    return "current owner" in str(exc)


def _follow_up_prompt(action: str) -> str | None:
    return {
        "postpone": "请回复新的截止时间，例如：延期到明天下午六点",
        "set_due_at": "请回复截止时间，例如：改到明天下午六点",
        "set_owner": "请回复负责人，例如：负责人改成李珍",
        "set_completion_criteria": "请回复完成标准，例如：完成标准是列出三条动作",
    }.get(action)
