from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings, load_yaml_config
from app.database import SessionLocal
from app.integrations.dingtalk_client import DingTalkClient
from app.schemas import ReminderRunRead
from app.services.reminder_service import run_reminder_cycle, send_reminder_dispatches


def scheduled_reminder_times(config: dict | None = None) -> list[str]:
    reminders = (config or load_yaml_config("dingtalk_config.yaml")).get("reminders", {})
    return sorted(set(reminders.values()))


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
