from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.api.reports import get_weekly_report_endpoint
from app.schemas import WeeklyReportRead


@pytest.mark.asyncio
async def test_get_weekly_report_endpoint_returns_report(monkeypatch) -> None:
    period_start = datetime(2026, 5, 11, tzinfo=UTC)
    period_end = datetime(2026, 5, 18, tzinfo=UTC)
    as_of = datetime(2026, 5, 18, 9, 0, tzinfo=UTC)

    async def fake_generate_weekly_report(session, **kwargs):
        assert kwargs == {
            "period_start": period_start,
            "period_end": period_end,
            "as_of": as_of,
        }
        return WeeklyReportRead(
            period_start=period_start,
            period_end=period_end,
            created_count=2,
            completed_count=1,
            overdue_open_count=1,
            postponed_count=0,
            waiting_count=1,
            waiting_by_user={"u-1": 1},
            blocked_count=0,
            stale_tdls=[],
            due_next_week_count=1,
            created_by_business_line={"励步英语": 2},
        )

    monkeypatch.setattr(
        "app.api.reports.generate_weekly_report",
        fake_generate_weekly_report,
    )

    result = await get_weekly_report_endpoint(
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        session=None,
    )

    assert result.created_count == 2
    assert result.waiting_by_user == {"u-1": 1}


@pytest.mark.asyncio
async def test_get_weekly_report_endpoint_rejects_invalid_period() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_weekly_report_endpoint(
            period_start=datetime(2026, 5, 18, tzinfo=UTC),
            period_end=datetime(2026, 5, 11, tzinfo=UTC),
            as_of=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
            session=None,
        )

    assert exc.value.status_code == 400
