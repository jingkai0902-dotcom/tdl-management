from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.dingtalk_client import DingTalkClient
from app.models import AuditLog, TDL
from app.schemas import WeeklyReportRead, WeeklyReportStaleTDLRead


OPEN_STATUSES = {"active", "snoozed", "attention"}
EXCLUDED_FROM_CREATED_COUNT = {"draft", "canceled"}
REPORT_AUDIT_ACTIONS = {"complete", "postpone"}


def _in_period(value: datetime | None, start: datetime, end: datetime) -> bool:
    return value is not None and start <= value < end


def _is_open(tdl: TDL) -> bool:
    return tdl.status in OPEN_STATUSES


def build_weekly_report(
    tdls: list[TDL],
    audit_logs: list[AuditLog],
    *,
    period_start: datetime,
    period_end: datetime,
    as_of: datetime,
) -> WeeklyReportRead:
    open_tdls = [tdl for tdl in tdls if _is_open(tdl)]
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
    postponed_tdl_ids = {
        audit.entity_id
        for audit in audit_logs
        if audit.entity_type == "tdl"
        and audit.action == "postpone"
        and _in_period(audit.created_at, period_start, period_end)
    }

    waiting_tdls = [tdl for tdl in open_tdls if tdl.waiting_for]
    waiting_by_user = Counter(
        waiting_user_id
        for tdl in waiting_tdls
        for waiting_user_id in tdl.waiting_for
    )
    stale_tdls = []
    for tdl in open_tdls:
        touched_at = tdl.updated_at or tdl.created_at
        if touched_at is None:
            continue
        inactive_for = as_of - touched_at
        if inactive_for <= timedelta(days=3):
            continue
        stale_tdls.append(
            WeeklyReportStaleTDLRead(
                tdl_id=tdl.tdl_id,
                title=tdl.title,
                days_without_progress=inactive_for.days,
            )
        )

    stale_tdls.sort(key=lambda item: item.days_without_progress, reverse=True)
    next_week_end = period_end + timedelta(days=7)
    created_by_business_line = Counter(
        tdl.business_line or "未分类" for tdl in reportable_created_tdls
    )

    return WeeklyReportRead(
        period_start=period_start,
        period_end=period_end,
        created_count=len(reportable_created_tdls),
        completed_count=len(completed_tdl_ids),
        overdue_open_count=sum(
            1 for tdl in open_tdls if tdl.due_at is not None and tdl.due_at < as_of
        ),
        postponed_count=len(postponed_tdl_ids),
        waiting_count=len(waiting_tdls),
        waiting_by_user=dict(waiting_by_user),
        blocked_count=sum(1 for tdl in open_tdls if tdl.blocked_by),
        stale_tdls=stale_tdls,
        due_next_week_count=sum(
            1
            for tdl in open_tdls
            if tdl.due_at is not None and period_end <= tdl.due_at < next_week_end
        ),
        created_by_business_line=dict(created_by_business_line),
    )


async def generate_weekly_report(
    session: AsyncSession,
    *,
    period_start: datetime,
    period_end: datetime,
    as_of: datetime,
) -> WeeklyReportRead:
    tdl_result = await session.execute(select(TDL))
    audit_result = await session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "tdl",
            AuditLog.action.in_(REPORT_AUDIT_ACTIONS),
            AuditLog.created_at >= period_start,
            AuditLog.created_at < period_end,
        )
    )
    return build_weekly_report(
        list(tdl_result.scalars().all()),
        list(audit_result.scalars().all()),
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
    )


def render_weekly_report_markdown(report: WeeklyReportRead) -> str:
    stale_lines = [
        f"- {item.title}：{item.days_without_progress} 天未推进"
        for item in report.stale_tdls
    ] or ["- 无"]
    waiting_lines = [
        f"- {owner_id}：{count} 条"
        for owner_id, count in sorted(report.waiting_by_user.items())
    ] or ["- 无"]
    business_lines = [
        f"- {business_line}：{count} 条"
        for business_line, count in sorted(report.created_by_business_line.items())
    ] or ["- 无"]
    return "\n".join(
        [
            "## 周报事实账本",
            "",
            f"- 新增：{report.created_count}",
            f"- 完成：{report.completed_count}",
            f"- 逾期未完成：{report.overdue_open_count}",
            f"- 本周延期：{report.postponed_count}",
            f"- 等待中：{report.waiting_count}",
            f"- 阻塞中：{report.blocked_count}",
            f"- 下周到期：{report.due_next_week_count}",
            "",
            "### 等待对象",
            *waiting_lines,
            "",
            "### 超过 3 天未推进",
            *stale_lines,
            "",
            "### 新增任务按业务线",
            *business_lines,
        ]
    )


def weekly_report_recipients(config: dict | None = None) -> list[str]:
    weekly_report = (config or load_yaml_config("dingtalk_config.yaml")).get(
        "weekly_report",
        {},
    )
    return list(weekly_report.get("recipient_user_ids", []))


async def send_weekly_report(
    client: DingTalkClient,
    report: WeeklyReportRead,
    *,
    recipient_user_ids: list[str] | None = None,
) -> int:
    recipients = (
        recipient_user_ids if recipient_user_ids is not None else weekly_report_recipients()
    )
    if not recipients:
        return 0
    await client.send_work_markdown(
        user_ids=recipients,
        title="周报事实账本",
        text=render_weekly_report_markdown(report),
    )
    return len(recipients)