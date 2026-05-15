from datetime import UTC, datetime

import pytest

from app.api.reminders import run_reminder_cycle_endpoint
from app.schemas import ReminderDispatchRead, ReminderRunRead, TDLCardRead


@pytest.mark.asyncio
async def test_run_reminder_cycle_endpoint_returns_batch(monkeypatch) -> None:
    as_of = datetime(2026, 5, 18, 8, 30, tzinfo=UTC)

    async def fake_run_reminder_cycle(session, *, as_of):
        assert as_of == datetime(2026, 5, 18, 8, 30, tzinfo=UTC)
        return ReminderRunRead(
            candidate_count=1,
            marked_attention_count=0,
            dispatches=[
                ReminderDispatchRead(
                    owner_id="owner-1",
                    action="due_today",
                    overdue_days=0,
                    card=TDLCardRead(
                        title="今日待办",
                        body=["测试任务"],
                        buttons=[],
                        status="active",
                    ),
                )
            ],
        )

    monkeypatch.setattr("app.api.reminders.run_reminder_cycle", fake_run_reminder_cycle)

    result = await run_reminder_cycle_endpoint(as_of=as_of, session=None)

    assert result.candidate_count == 1
    assert result.dispatches[0].owner_id == "owner-1"
