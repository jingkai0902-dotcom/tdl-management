from datetime import UTC, datetime

import pytest

from app.schemas import ReminderRunRead
from app.workers.scheduler import (
    build_scheduler,
    run_scheduled_reminder_cycle,
    run_scheduled_weekly_report,
    scheduled_reminder_times,
    scheduled_weekly_report_time,
)


class FakeSessionContext:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeDingTalkClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_scheduled_reminder_times_deduplicates_config_values() -> None:
    assert scheduled_reminder_times(
        {
            "reminders": {
                "teacher_shift": "08:30",
                "operations_shift": "08:30",
                "operations_shift_tuesday": "10:00",
                "standard_shift": "08:30",
            }
        }
    ) == ["08:30", "10:00"]


def test_build_scheduler_registers_one_job_per_distinct_time() -> None:
    scheduler = build_scheduler(
        config={
            "reminders": {
                "teacher_shift": "08:30",
                "operations_shift_tuesday": "10:00",
                "standard_shift": "08:30",
            }
        },
        timezone_name="Asia/Shanghai",
    )

    assert sorted(job.id for job in scheduler.get_jobs()) == [
        "reminders-0830",
        "reminders-1000",
        "weekly-report",
    ]


def test_scheduled_weekly_report_time_reads_config() -> None:
    assert scheduled_weekly_report_time({"weekly_report": {"time": "09:30"}}) == "09:30"


@pytest.mark.asyncio
async def test_run_scheduled_reminder_cycle_sends_dispatches(monkeypatch) -> None:
    expected = ReminderRunRead(candidate_count=0, marked_attention_count=0, dispatches=[])
    fake_client = FakeDingTalkClient()

    async def fake_run_reminder_cycle(session, *, as_of):
        assert session == "session"
        assert as_of == datetime(2026, 5, 18, 8, 30, tzinfo=UTC)
        return expected

    async def fake_send_reminder_dispatches(client, dispatches):
        assert client is fake_client
        assert dispatches == []
        return 0

    monkeypatch.setattr("app.workers.scheduler.run_reminder_cycle", fake_run_reminder_cycle)
    monkeypatch.setattr(
        "app.workers.scheduler.send_reminder_dispatches",
        fake_send_reminder_dispatches,
    )

    result = await run_scheduled_reminder_cycle(
        as_of=datetime(2026, 5, 18, 8, 30, tzinfo=UTC),
        session_factory=FakeSessionContext,
        client_factory=lambda: fake_client,
    )

    assert result == expected
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_run_scheduled_weekly_report_sends_report(monkeypatch) -> None:
    fake_client = FakeDingTalkClient()
    expected = object()

    async def fake_generate_weekly_report(session, *, period_start, period_end, as_of):
        assert session == "session"
        assert period_start == datetime(2026, 5, 11, 0, 0, tzinfo=UTC)
        assert period_end == datetime(2026, 5, 18, 0, 0, tzinfo=UTC)
        assert as_of == datetime(2026, 5, 18, 9, 0, tzinfo=UTC)
        return expected

    async def fake_send_weekly_report(client, report):
        assert client is fake_client
        assert report is expected
        return 1

    monkeypatch.setattr(
        "app.workers.scheduler.generate_weekly_report",
        fake_generate_weekly_report,
    )
    monkeypatch.setattr(
        "app.workers.scheduler.send_weekly_report",
        fake_send_weekly_report,
    )

    result = await run_scheduled_weekly_report(
        as_of=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
        session_factory=FakeSessionContext,
        client_factory=lambda: fake_client,
    )

    assert result is expected
    assert fake_client.closed is True