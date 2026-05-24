from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TDL
from app.roster import format_management_name
from app.schemas import TDLRead, WorkbenchRead, WorkbenchSectionRead, WorkbenchTDLRead


OPEN_STATUSES = {"active", "attention", "snoozed"}
PENDING_STATUSES = {"draft"}
TDL_DATA_SOURCE = "tdls"


def _start_of_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_week(value: datetime) -> datetime:
    start = _start_of_day(value)
    days_until_next_monday = 7 - start.weekday()
    return start + timedelta(days=days_until_next_monday)


def _is_open(tdl: TDL) -> bool:
    return tdl.status in OPEN_STATUSES


def _has_due_between(tdl: TDL, start: datetime, end: datetime) -> bool:
    return tdl.due_at is not None and start <= tdl.due_at < end


def _sort_tdls(tdls: list[TDL]) -> list[TDL]:
    return sorted(
        tdls,
        key=lambda tdl: (
            tdl.due_at is None,
            tdl.due_at or datetime.max.replace(tzinfo=None),
            tdl.priority,
            tdl.created_at or datetime.max.replace(tzinfo=None),
            tdl.title,
        ),
    )


def _section(key: str, title: str, tdls: list[TDL]) -> WorkbenchSectionRead:
    items = []
    for tdl in _sort_tdls(tdls):
        tdl_read = TDLRead.from_tdl(tdl)
        items.append(
            WorkbenchTDLRead(
                **tdl_read.model_dump(),
                owner_label=format_management_name(tdl.owner_id) or tdl.owner_id,
            )
        )
    return WorkbenchSectionRead(
        key=key,
        title=title,
        count=len(items),
        data_source=TDL_DATA_SOURCE,
        items=items,
    )


def build_workbench_summary(tdls: list[TDL], *, as_of: datetime) -> WorkbenchRead:
    today_start = _start_of_day(as_of)
    tomorrow_start = today_start + timedelta(days=1)
    week_end = _end_of_week(as_of)
    soon_end = as_of + timedelta(hours=24)
    open_tdls = [tdl for tdl in tdls if _is_open(tdl)]

    return WorkbenchRead(
        as_of=as_of,
        data_source=TDL_DATA_SOURCE,
        sections=[
            _section(
                "today",
                "今日",
                [
                    tdl
                    for tdl in open_tdls
                    if _has_due_between(tdl, today_start, tomorrow_start)
                ],
            ),
            _section(
                "this_week",
                "本周剩余",
                [
                    tdl
                    for tdl in open_tdls
                    if _has_due_between(tdl, today_start, week_end)
                ],
            ),
            _section(
                "overdue_or_due_soon",
                "逾期 / 临期",
                [
                    tdl
                    for tdl in open_tdls
                    if tdl.due_at is not None and tdl.due_at < soon_end
                ],
            ),
            _section("in_progress", "进行中", open_tdls),
            _section(
                "pending_confirmation",
                "待确认 / 待判断",
                [tdl for tdl in tdls if tdl.status in PENDING_STATUSES],
            ),
        ],
    )


async def generate_workbench_summary(
    session: AsyncSession,
    *,
    as_of: datetime,
    owner_id: str | None = None,
) -> WorkbenchRead:
    query = select(TDL)
    if owner_id is not None:
        query = query.where(TDL.owner_id == owner_id)
    result = await session.execute(query)
    return build_workbench_summary(
        list(result.scalars().all()),
        as_of=as_of,
    )
