from datetime import UTC, datetime
from uuid import uuid4

from app.models import AuditLog, TDL
from app.services.review_service import build_weekly_report


def _tdl(
    *,
    status: str,
    created_at: datetime,
    updated_at: datetime,
    due_at: datetime | None = None,
    waiting_for: list[str] | None = None,
    blocked_by: list[str] | None = None,
    business_line: str | None = None,
) -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title="测试任务",
        owner_id="owner-1",
        due_at=due_at,
        status=status,
        priority="P2",
        created_by="owner-1",
        created_at=created_at,
        updated_at=updated_at,
        waiting_for=waiting_for or [],
        blocked_by=blocked_by or [],
        business_line=business_line,
        source="manual",
    )


def _audit(*, entity_id: str, action: str, created_at: datetime) -> AuditLog:
    return AuditLog(
        entity_type="tdl",
        entity_id=entity_id,
        action=action,
        actor_id="owner-1",
        payload={},
        created_at=created_at,
    )


def test_build_weekly_report_counts_current_facts() -> None:
    period_start = datetime(2026, 5, 11, tzinfo=UTC)
    period_end = datetime(2026, 5, 18, tzinfo=UTC)
    as_of = datetime(2026, 5, 18, 9, 0, tzinfo=UTC)

    overdue_waiting = _tdl(
        status="active",
        created_at=datetime(2026, 5, 12, tzinfo=UTC),
        updated_at=datetime(2026, 5, 12, tzinfo=UTC),
        due_at=datetime(2026, 5, 16, tzinfo=UTC),
        waiting_for=["u-1", "u-2"],
        business_line="励步英语",
    )
    completed = _tdl(
        status="done",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
        updated_at=datetime(2026, 5, 14, tzinfo=UTC),
        business_line="斯坦星球",
    )
    blocked_due_next_week = _tdl(
        status="active",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 13, tzinfo=UTC),
        due_at=datetime(2026, 5, 20, tzinfo=UTC),
        waiting_for=["u-1"],
        blocked_by=[str(uuid4())],
        business_line="飞书工资",
    )
    draft = _tdl(
        status="draft",
        created_at=datetime(2026, 5, 15, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, tzinfo=UTC),
        business_line="励步英语",
    )

    report = build_weekly_report(
        [overdue_waiting, completed, blocked_due_next_week, draft],
        [
            _audit(
                entity_id=str(completed.tdl_id),
                action="complete",
                created_at=datetime(2026, 5, 14, tzinfo=UTC),
            ),
            _audit(
                entity_id=str(blocked_due_next_week.tdl_id),
                action="postpone",
                created_at=datetime(2026, 5, 15, tzinfo=UTC),
            ),
        ],
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
    )

    assert report.created_count == 2
    assert report.completed_count == 1
    assert report.overdue_open_count == 1
    assert report.postponed_count == 1
    assert report.waiting_count == 2
    assert report.waiting_by_user == {"u-1": 2, "u-2": 1}
    assert report.blocked_count == 1
    assert [tdl.tdl_id for tdl in report.stale_tdls] == [
        overdue_waiting.tdl_id,
        blocked_due_next_week.tdl_id,
    ]
    assert [tdl.days_without_progress for tdl in report.stale_tdls] == [6, 5]
    assert report.due_next_week_count == 1
    assert report.created_by_business_line == {"励步英语": 1, "斯坦星球": 1}
