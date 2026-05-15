from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.models import AuditLog, TDL
from app.schemas import ReminderCandidateRead


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
