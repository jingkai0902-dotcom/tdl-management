from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.dingtalk_card import build_reminder_card, render_markdown
from app.integrations.dingtalk_client import DingTalkClient
from app.models import AuditLog, TDL
from app.schemas import (
    ReminderCandidateRead,
    ReminderDispatchRead,
    ReminderRunRead,
    TDLCardRead,
)


OPEN_STATUSES = {"active", "attention", "snoozed"}
DEFAULT_SHIFT_TYPE = "standard_shift"


def build_reminder_candidates(
    tdls: list[TDL],
    *,
    as_of: datetime,
    policy: dict | None = None,
) -> list[ReminderCandidateRead]:
    resolved_policy = policy or load_yaml_config("escalation_policy.yaml").get("mvp", {})
    candidates = []

    for tdl in tdls:
        if not _is_remindable(tdl, as_of):
            continue
        overdue_days = _overdue_days(tdl, as_of)
        action = _action_for_overdue_days(overdue_days, resolved_policy)
        if action is None:
            continue
        candidates.append(
            ReminderCandidateRead(
                tdl_id=tdl.tdl_id,
                owner_id=tdl.owner_id,
                title=tdl.title,
                action=action,
                overdue_days=overdue_days,
            )
        )

    return candidates


async def collect_reminder_candidates(
    session: AsyncSession,
    *,
    as_of: datetime,
) -> list[ReminderCandidateRead]:
    result = await session.execute(select(TDL))
    return build_reminder_candidates(list(result.scalars().all()), as_of=as_of)


async def mark_attention_tdls(
    session: AsyncSession,
    candidates: list[ReminderCandidateRead],
) -> list[TDL]:
    marked = []
    for candidate in candidates:
        if candidate.action != "mark_attention":
            continue
        tdl = await session.get(TDL, candidate.tdl_id)
        if tdl is None or tdl.status == "attention":
            continue
        tdl.status = "attention"
        session.add(
            AuditLog(
                entity_type="tdl",
                entity_id=str(tdl.tdl_id),
                action="mark_attention",
                actor_id=None,
                payload={"overdue_days": candidate.overdue_days},
            )
        )
        marked.append(tdl)

    await session.commit()
    for tdl in marked:
        await session.refresh(tdl)
    return marked


def build_sendable_reminder_cards(
    tdls: list[TDL],
    candidates: list[ReminderCandidateRead],
    *,
    yesterday_completed_by_owner: dict[str, int] | None = None,
) -> list[ReminderDispatchRead]:
    tdl_by_id = {tdl.tdl_id: tdl for tdl in tdls}
    counts_by_owner = yesterday_completed_by_owner or {}
    owners_with_completion_line = set()
    dispatches = []
    for candidate in candidates:
        if candidate.action == "mark_attention":
            continue
        tdl = tdl_by_id.get(candidate.tdl_id)
        if tdl is None:
            continue
        yesterday_completed_count = None
        if candidate.owner_id not in owners_with_completion_line:
            yesterday_completed_count = counts_by_owner.get(candidate.owner_id, 0)
            owners_with_completion_line.add(candidate.owner_id)
        dispatches.append(
            ReminderDispatchRead(
                owner_id=candidate.owner_id,
                action=candidate.action,
                overdue_days=candidate.overdue_days,
                card=TDLCardRead.model_validate(
                    build_reminder_card(
                        tdl,
                        action=candidate.action,
                        overdue_days=candidate.overdue_days,
                        yesterday_completed_count=yesterday_completed_count,
                    )
                ),
            )
        )
    return dispatches


async def run_reminder_cycle(
    session: AsyncSession,
    *,
    as_of: datetime,
    roster: dict | None = None,
    dingtalk_config: dict | None = None,
) -> ReminderRunRead:
    result = await session.execute(select(TDL))
    tdls = list(result.scalars().all())
    candidates = filter_due_candidates_for_run(
        build_reminder_candidates(tdls, as_of=as_of),
        as_of=as_of,
        roster=roster,
        config=dingtalk_config,
    )
    marked_attention = await mark_attention_tdls(session, candidates)
    completion_result = await session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "tdl",
            AuditLog.action == "complete",
            AuditLog.created_at >= _previous_day_start(as_of),
            AuditLog.created_at < _current_day_start(as_of),
        )
    )
    dispatches = build_sendable_reminder_cards(
        tdls,
        candidates,
        yesterday_completed_by_owner=count_yesterday_completions(
            list(completion_result.scalars().all()),
            as_of=as_of,
        ),
    )
    return ReminderRunRead(
        candidate_count=len(candidates),
        marked_attention_count=len(marked_attention),
        dispatches=dispatches,
    )


def filter_due_candidates_for_run(
    candidates: list[ReminderCandidateRead],
    *,
    as_of: datetime,
    roster: dict | None = None,
    config: dict | None = None,
) -> list[ReminderCandidateRead]:
    current_time = as_of.strftime("%H:%M")
    return [
        candidate
        for candidate in candidates
        if reminder_time_for_owner(
            candidate.owner_id,
            as_of=as_of,
            roster=roster,
            config=config,
        )
        == current_time
    ]


async def send_reminder_dispatches(
    client: DingTalkClient,
    dispatches: list[ReminderDispatchRead],
) -> int:
    for dispatch in dispatches:
        await client.send_work_markdown(
            user_ids=[dispatch.owner_id],
            title=dispatch.card.title,
            text=render_markdown(dispatch.card),
        )
    return len(dispatches)


def _is_remindable(tdl: TDL, as_of: datetime) -> bool:
    if tdl.status not in OPEN_STATUSES:
        return False
    if tdl.owner_id is None or tdl.due_at is None:
        return False
    if tdl.snooze_until is not None and tdl.snooze_until > as_of:
        return False
    return True


def _overdue_days(tdl: TDL, as_of: datetime) -> int:
    due_at = tdl.due_at
    if due_at is not None and due_at.tzinfo is not None and as_of.tzinfo is not None:
        due_at = due_at.astimezone(as_of.tzinfo)
    day_delta = as_of.date() - due_at.date()
    return day_delta.days


def _action_for_overdue_days(overdue_days: int, policy: dict) -> str | None:
    if overdue_days < 0:
        return None
    if overdue_days == 0:
        return "due_today"
    if overdue_days == 1:
        return policy.get("overdue_day_1")
    if overdue_days == 2:
        return policy.get("overdue_day_2")
    if overdue_days >= 3:
        return policy.get("overdue_day_3")
    return None


def count_yesterday_completions(
    audit_logs: list[AuditLog],
    *,
    as_of: datetime,
) -> dict[str, int]:
    previous_day_start = _previous_day_start(as_of)
    current_day_start = _current_day_start(as_of)
    return dict(
        Counter(
            audit.actor_id
            for audit in audit_logs
            if audit.entity_type == "tdl"
            and audit.action == "complete"
            and audit.actor_id is not None
            and audit.created_at is not None
            and previous_day_start <= audit.created_at < current_day_start
        )
    )


def _previous_day_start(as_of: datetime) -> datetime:
    return _current_day_start(as_of) - timedelta(days=1)


def _current_day_start(as_of: datetime) -> datetime:
    return as_of.replace(hour=0, minute=0, second=0, microsecond=0)


def reminder_time_for_shift(
    shift_type: str | None,
    *,
    as_of: datetime,
    config: dict | None = None,
) -> str:
    reminders = (config or load_yaml_config("dingtalk_config.yaml")).get("reminders", {})
    resolved_shift = shift_type or DEFAULT_SHIFT_TYPE
    if resolved_shift == "operations_shift" and as_of.weekday() == 1:
        return reminders.get("operations_shift_tuesday", reminders.get("operations_shift", "08:30"))
    return reminders.get(resolved_shift, reminders.get(DEFAULT_SHIFT_TYPE, "08:30"))


def shift_type_for_owner(
    owner_id: str,
    *,
    roster: dict | None = None,
) -> str | None:
    management = (roster or load_yaml_config("management_roster.yaml")).get("management", [])
    for manager in management:
        if manager.get("dingtalk_user_id") == owner_id:
            return manager.get("shift_type")
    return None


def reminder_time_for_owner(
    owner_id: str,
    *,
    as_of: datetime,
    roster: dict | None = None,
    config: dict | None = None,
) -> str:
    return reminder_time_for_shift(
        shift_type_for_owner(owner_id, roster=roster),
        as_of=as_of,
        config=config,
    )
