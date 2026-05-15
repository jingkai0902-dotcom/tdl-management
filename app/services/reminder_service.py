from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.dingtalk_card import build_reminder_card
from app.models import AuditLog, TDL
from app.schemas import (
    ReminderCandidateRead,
    ReminderDispatchRead,
    ReminderRunRead,
    TDLCardRead,
)


OPEN_STATUSES = {"active", "attention", "snoozed"}


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
) -> ReminderRunRead:
    result = await session.execute(select(TDL))
    tdls = list(result.scalars().all())
    candidates = build_reminder_candidates(tdls, as_of=as_of)
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


def _is_remindable(tdl: TDL, as_of: datetime) -> bool:
    if tdl.status not in OPEN_STATUSES:
        return False
    if tdl.owner_id is None or tdl.due_at is None:
        return False
    if tdl.snooze_until is not None and tdl.snooze_until > as_of:
        return False
    return True


def _overdue_days(tdl: TDL, as_of: datetime) -> int:
    day_delta = as_of.date() - tdl.due_at.date()
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
