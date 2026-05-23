from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, IntakeDiffLog, IntakeQueueItem, TDL


OPEN_STATUSES = {"active", "attention", "snoozed"}
EXCLUDED_FROM_CREATED_COUNT = {"draft", "canceled"}


@dataclass(frozen=True)
class PilotMetrics:
    period_start: datetime
    period_end: datetime
    weekly_active_users: int
    created_count: int
    completed_count: int
    closure_rate: float | None
    draft_created_count: int
    draft_confirmed_count: int
    draft_confirmation_rate: float | None
    active_tdl_count: int
    active_tdl_with_calendar_count: int
    calendar_event_generation_rate: float | None
    average_response_seconds: float | None
    ignored_draft_count: int
    ignore_rate: float | None
    open_status_counts: dict[str, int]


def _in_period(value: datetime | None, start: datetime, end: datetime) -> bool:
    return value is not None and start <= value < end


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _draft_count(
    *,
    intake_diff_logs: list[IntakeDiffLog],
    audit_logs: list[AuditLog],
    diff_action: str,
    audit_action: str,
    period_start: datetime,
    period_end: datetime,
) -> int:
    diff_count = sum(
        1
        for item in intake_diff_logs
        if item.action_type == diff_action
        and _in_period(item.created_at, period_start, period_end)
    )
    if diff_count > 0:
        return diff_count
    return sum(
        1
        for audit in audit_logs
        if audit.entity_type == "tdl"
        and audit.action == audit_action
        and _in_period(audit.created_at, period_start, period_end)
    )


def build_pilot_metrics(
    tdls: list[TDL],
    audit_logs: list[AuditLog],
    intake_diff_logs: list[IntakeDiffLog],
    intake_queue_items: list[IntakeQueueItem],
    *,
    period_start: datetime,
    period_end: datetime,
) -> PilotMetrics:
    reportable_created_tdls = [
        tdl
        for tdl in tdls
        if tdl.status not in EXCLUDED_FROM_CREATED_COUNT
        and _in_period(tdl.created_at, period_start, period_end)
    ]
    completed_tdl_ids = {
        audit.entity_id
        for audit in audit_logs
        if audit.entity_type == "tdl"
        and audit.action == "complete"
        and _in_period(audit.created_at, period_start, period_end)
    }
    draft_created_count = _draft_count(
        intake_diff_logs=intake_diff_logs,
        audit_logs=audit_logs,
        diff_action="draft_created",
        audit_action="draft_create",
        period_start=period_start,
        period_end=period_end,
    )
    draft_confirmed_count = _draft_count(
        intake_diff_logs=intake_diff_logs,
        audit_logs=audit_logs,
        diff_action="confirmed",
        audit_action="confirm",
        period_start=period_start,
        period_end=period_end,
    )
    ignored_draft_count = _draft_count(
        intake_diff_logs=intake_diff_logs,
        audit_logs=audit_logs,
        diff_action="canceled",
        audit_action="cancel",
        period_start=period_start,
        period_end=period_end,
    )
    active_tdls = [tdl for tdl in tdls if tdl.status in OPEN_STATUSES]
    response_seconds = [
        (item.processed_at - item.created_at).total_seconds()
        for item in intake_queue_items
        if item.status == "done"
        and item.created_at is not None
        and item.processed_at is not None
        and _in_period(item.created_at, period_start, period_end)
    ]

    return PilotMetrics(
        period_start=period_start,
        period_end=period_end,
        weekly_active_users=len({tdl.created_by for tdl in reportable_created_tdls}),
        created_count=len(reportable_created_tdls),
        completed_count=len(completed_tdl_ids),
        closure_rate=_ratio(len(completed_tdl_ids), len(reportable_created_tdls)),
        draft_created_count=draft_created_count,
        draft_confirmed_count=draft_confirmed_count,
        draft_confirmation_rate=_ratio(draft_confirmed_count, draft_created_count),
        active_tdl_count=len(active_tdls),
        active_tdl_with_calendar_count=sum(1 for tdl in active_tdls if tdl.calendar_event_id),
        calendar_event_generation_rate=_ratio(
            sum(1 for tdl in active_tdls if tdl.calendar_event_id),
            len(active_tdls),
        ),
        average_response_seconds=(
            sum(response_seconds) / len(response_seconds) if response_seconds else None
        ),
        ignored_draft_count=ignored_draft_count,
        ignore_rate=_ratio(ignored_draft_count, draft_created_count),
        open_status_counts={
            status: sum(1 for tdl in active_tdls if tdl.status == status)
            for status in sorted(OPEN_STATUSES)
        },
    )


async def generate_pilot_metrics(
    session: AsyncSession,
    *,
    period_start: datetime,
    period_end: datetime,
) -> PilotMetrics:
    tdl_result = await session.execute(select(TDL))
    audit_result = await session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "tdl",
            AuditLog.action.in_(["complete", "draft_create", "confirm", "cancel"]),
            AuditLog.created_at >= period_start,
            AuditLog.created_at < period_end,
        )
    )
    diff_result = await session.execute(
        select(IntakeDiffLog).where(
            IntakeDiffLog.created_at >= period_start,
            IntakeDiffLog.created_at < period_end,
        )
    )
    queue_result = await session.execute(
        select(IntakeQueueItem).where(
            IntakeQueueItem.created_at >= period_start,
            IntakeQueueItem.created_at < period_end,
        )
    )
    return build_pilot_metrics(
        list(tdl_result.scalars().all()),
        list(audit_result.scalars().all()),
        list(diff_result.scalars().all()),
        list(queue_result.scalars().all()),
        period_start=period_start,
        period_end=period_end,
    )


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1%}"


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}s"


def _format_status_mix(counts: dict[str, int]) -> str:
    return " / ".join(f"{status} {counts.get(status, 0)}" for status in sorted(OPEN_STATUSES))


def render_pilot_metrics_markdown(metrics: PilotMetrics) -> str:
    return "\n".join(
        [
            "## Daily Pilot Metrics",
            "",
            f"- Period: {metrics.period_start.isoformat()} -> {metrics.period_end.isoformat()}",
            "",
            "| Metric | Value | Target |",
            "|---|---:|---:|",
            f"| Weekly active users | {metrics.weekly_active_users} | >= 2 |",
            f"| TDL closure rate | {_format_ratio(metrics.closure_rate)} "
            f"({metrics.completed_count}/{metrics.created_count}) | >= 60% |",
            f"| AI draft confirmation rate | {_format_ratio(metrics.draft_confirmation_rate)} "
            f"({metrics.draft_confirmed_count}/{metrics.draft_created_count}) | >= 70% |",
            f"| Calendar event generation rate | "
            f"{_format_ratio(metrics.calendar_event_generation_rate)} "
            f"({metrics.active_tdl_with_calendar_count}/{metrics.active_tdl_count}) | >= 90% |",
            f"| Open TDL status mix | {_format_status_mix(metrics.open_status_counts)} | diagnostic |",
            f"| Average response time | {_format_seconds(metrics.average_response_seconds)} | < 5s |",
            f"| Draft ignore rate | {_format_ratio(metrics.ignore_rate)} "
            f"({metrics.ignored_draft_count}/{metrics.draft_created_count}) | < 20% |",
        ]
    )
