from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings, load_yaml_config
from app.database import SessionLocal
from app.integrations.dingtalk_client import DingTalkClient
from app.schemas import ReminderRunRead, WeeklyReportRead
from app.services.reminder_service import run_reminder_cycle, send_reminder_dispatches
from app.services.review_service import generate_weekly_report, send_weekly_report


def scheduled_reminder_times(config: dict | None = None) -> list[str]:
    reminders = (config or load_yaml_config("dingtalk_config.yaml")).get("reminders", {})
    return sorted(set(reminders.values()))


def scheduled_weekly_report_time(config: dict | None = None) -> str:
    weekly_report = (config or load_yaml_config("dingtalk_config.yaml")).get(
        "weekly_report",
        {},
    )
    return weekly_report.get("time", "09:00")


def build_scheduler(
    *,
    config: dict | None = None,
    timezone_name: str | None = None,
) -> AsyncIOScheduler:
    settings = get_settings()
    timezone = ZoneInfo(timezone_name or settings.scheduler_timezone)
    scheduler = AsyncIOScheduler(timezone=timezone)
    for reminder_time in scheduled_reminder_times(config):
        hour, minute = reminder_time.split(":")
        scheduler.add_job(
            run_scheduled_reminder_cycle,
            "cron",
            id=f"reminders-{hour}{minute}",
            hour=int(hour),
            minute=int(minute),
            replace_existing=True,
        )
    report_hour, report_minute = scheduled_weekly_report_time(config).split(":")
    scheduler.add_job(
        run_scheduled_weekly_report,
        "cron",
        id="weekly-report",
        day_of_week="mon",
        hour=int(report_hour),
        minute=int(report_minute),
        replace_existing=True,
    )
    return scheduler


async def run_scheduled_reminder_cycle(
    *,
    as_of: datetime | None = None,
    session_factory=SessionLocal,
    client_factory=DingTalkClient,
) -> ReminderRunRead:
    settings = get_settings()
    effective_as_of = as_of or datetime.now(ZoneInfo(settings.scheduler_timezone))
    async with session_factory() as session:
        result = await run_reminder_cycle(session, as_of=effective_as_of)
    client = client_factory()
    try:
        await send_reminder_dispatches(client, result.dispatches)
    finally:
        await client.close()
    return result


async def run_scheduled_weekly_report(
    *,
    as_of: datetime | None = None,
    session_factory=SessionLocal,
    client_factory=DingTalkClient,
) -> WeeklyReportRead:
    settings = get_settings()
    effective_as_of = as_of or datetime.now(ZoneInfo(settings.scheduler_timezone))
    period_end = effective_as_of.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = period_end - timedelta(days=7)
    async with session_factory() as session:
        report = await generate_weekly_report(
            session,
            period_start=period_start,
            period_end=period_end,
            as_of=effective_as_of,
        )
    client = client_factory()
    try:
        await send_weekly_report(client, report)
    finally:
        await client.close()
    return report