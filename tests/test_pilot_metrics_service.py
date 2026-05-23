from datetime import UTC, datetime
import importlib.util
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.models import AuditLog, IntakeDiffLog, IntakeQueueItem, TDL
from app.services.pilot_metrics_service import (
    build_pilot_metrics,
    render_pilot_metrics_markdown,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _tdl(
    *,
    status: str,
    created_by: str,
    created_at: datetime,
    calendar_event_id: str | None = None,
) -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title="测试任务",
        owner_id=created_by,
        due_at=datetime(2026, 5, 22, tzinfo=UTC),
        status=status,
        priority="P2",
        source="dingtalk_msg",
        created_by=created_by,
        created_at=created_at,
        updated_at=created_at,
        calendar_event_id=calendar_event_id,
    )


def _audit(
    *,
    entity_id: str,
    created_at: datetime,
    action: str = "complete",
) -> AuditLog:
    return AuditLog(
        entity_type="tdl",
        entity_id=entity_id,
        action=action,
        actor_id="owner-1",
        payload={},
        created_at=created_at,
    )


def _diff(*, action_type: str, created_at: datetime) -> IntakeDiffLog:
    return IntakeDiffLog(
        tdl_id=uuid4(),
        message_id=str(uuid4()),
        raw_text="下周三前审核暑期班方案",
        action_type=action_type,
        source="dingtalk_msg",
        actor_id="owner-1",
        draft_payload=None,
        confirmed_payload={},
        diff_fields=[],
        created_at=created_at,
    )


def _queue_item(*, created_at: datetime, processed_at: datetime) -> IntakeQueueItem:
    return IntakeQueueItem(
        intake_id=uuid4(),
        message_id=str(uuid4()),
        sender_id="owner-1",
        content="下周三前审核暑期班方案",
        status="done",
        attempts=1,
        max_attempts=3,
        created_at=created_at,
        processed_at=processed_at,
    )


def test_build_pilot_metrics_counts_six_pilot_indicators() -> None:
    period_start = datetime(2026, 5, 18, tzinfo=UTC)
    period_end = datetime(2026, 5, 25, tzinfo=UTC)
    created = _tdl(
        status="active",
        created_by="owner-1",
        created_at=datetime(2026, 5, 19, tzinfo=UTC),
        calendar_event_id="event-1",
    )
    completed = _tdl(
        status="done",
        created_by="owner-2",
        created_at=datetime(2026, 5, 20, tzinfo=UTC),
    )
    draft = _tdl(
        status="draft",
        created_by="owner-3",
        created_at=datetime(2026, 5, 21, tzinfo=UTC),
    )
    canceled = _tdl(
        status="canceled",
        created_by="owner-4",
        created_at=datetime(2026, 5, 22, tzinfo=UTC),
    )
    outside_period = _tdl(
        status="active",
        created_by="owner-5",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    attention = _tdl(
        status="attention",
        created_by="owner-6",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    snoozed = _tdl(
        status="snoozed",
        created_by="owner-7",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        calendar_event_id="event-2",
    )

    metrics = build_pilot_metrics(
        [created, completed, draft, canceled, outside_period, attention, snoozed],
        [_audit(entity_id=str(completed.tdl_id), created_at=datetime(2026, 5, 20, tzinfo=UTC))],
        [
            _diff(action_type="draft_created", created_at=datetime(2026, 5, 19, tzinfo=UTC)),
            _diff(action_type="draft_created", created_at=datetime(2026, 5, 20, tzinfo=UTC)),
            _diff(action_type="confirmed", created_at=datetime(2026, 5, 20, tzinfo=UTC)),
            _diff(action_type="canceled", created_at=datetime(2026, 5, 21, tzinfo=UTC)),
        ],
        [
            _queue_item(
                created_at=datetime(2026, 5, 19, 8, 0, 0, tzinfo=UTC),
                processed_at=datetime(2026, 5, 19, 8, 0, 4, tzinfo=UTC),
            ),
            _queue_item(
                created_at=datetime(2026, 5, 19, 8, 1, 0, tzinfo=UTC),
                processed_at=datetime(2026, 5, 19, 8, 1, 6, tzinfo=UTC),
            ),
        ],
        period_start=period_start,
        period_end=period_end,
    )

    assert metrics.weekly_active_users == 2
    assert metrics.created_count == 2
    assert metrics.completed_count == 1
    assert metrics.closure_rate == 0.5
    assert metrics.draft_created_count == 2
    assert metrics.draft_confirmed_count == 1
    assert metrics.draft_confirmation_rate == 0.5
    assert metrics.active_tdl_count == 4
    assert metrics.active_tdl_with_calendar_count == 2
    assert metrics.calendar_event_generation_rate == 0.5
    assert metrics.open_status_counts == {"active": 2, "attention": 1, "snoozed": 1}
    assert metrics.average_response_seconds == 5.0
    assert metrics.ignored_draft_count == 1
    assert metrics.ignore_rate == 0.5


def test_build_pilot_metrics_falls_back_to_audit_logs_for_draft_counts() -> None:
    period_start = datetime(2026, 5, 18, tzinfo=UTC)
    period_end = datetime(2026, 5, 25, tzinfo=UTC)

    metrics = build_pilot_metrics(
        [],
        [
            _audit(
                entity_id="tdl-1",
                action="draft_create",
                created_at=datetime(2026, 5, 19, tzinfo=UTC),
            ),
            _audit(
                entity_id="tdl-2",
                action="draft_create",
                created_at=datetime(2026, 5, 20, tzinfo=UTC),
            ),
            _audit(
                entity_id="tdl-1",
                action="confirm",
                created_at=datetime(2026, 5, 20, tzinfo=UTC),
            ),
            _audit(
                entity_id="tdl-2",
                action="cancel",
                created_at=datetime(2026, 5, 21, tzinfo=UTC),
            ),
        ],
        [],
        [],
        period_start=period_start,
        period_end=period_end,
    )

    assert metrics.draft_created_count == 2
    assert metrics.draft_confirmed_count == 1
    assert metrics.draft_confirmation_rate == 0.5
    assert metrics.ignored_draft_count == 1
    assert metrics.ignore_rate == 0.5


def test_render_pilot_metrics_markdown_keeps_targets_visible() -> None:
    period_start = datetime(2026, 5, 18, tzinfo=UTC)
    period_end = datetime(2026, 5, 25, tzinfo=UTC)
    metrics = build_pilot_metrics(
        [],
        [],
        [],
        [],
        period_start=period_start,
        period_end=period_end,
    )

    result = render_pilot_metrics_markdown(metrics)

    assert "## Daily Pilot Metrics" in result
    assert "| Weekly active users | 0 | >= 2 |" in result
    assert "| TDL closure rate | N/A (0/0) | >= 60% |" in result
    assert "| Open TDL status mix | active 0 / attention 0 / snoozed 0 | diagnostic |" in result
    assert "| Average response time | N/A | < 5s |" in result


def test_export_script_default_period_is_week_to_date_in_shanghai() -> None:
    module = _load_export_script()

    period_start, period_end = module._default_period(datetime(2026, 5, 22).date())

    assert period_start == datetime(2026, 5, 18, tzinfo=SHANGHAI_TZ)
    assert period_end == datetime(2026, 5, 23, tzinfo=SHANGHAI_TZ)


def test_append_ledger_replaces_same_day_block(tmp_path) -> None:
    module = _load_export_script()
    ledger = tmp_path / "daily-pilot-metrics.md"
    ledger.write_text("# 日常 TDL 助手试点指标\n", encoding="utf-8")

    module.append_ledger(
        ledger,
        "## Daily Pilot Metrics\n\nfirst",
        entry_date=datetime(2026, 5, 22).date(),
    )
    module.append_ledger(
        ledger,
        "## Daily Pilot Metrics\n\nsecond",
        entry_date=datetime(2026, 5, 22).date(),
    )

    result = ledger.read_text(encoding="utf-8")
    assert result.count("pilot-metrics:2026-05-22:begin") == 1
    assert "first" not in result
    assert "second" in result


def test_append_ledger_adds_auto_export_heading_once(tmp_path) -> None:
    module = _load_export_script()
    ledger = tmp_path / "daily-pilot-metrics.md"
    ledger.write_text("# 日常 TDL 助手试点指标\n", encoding="utf-8")

    module.append_ledger(
        ledger,
        "## Daily Pilot Metrics\n\nfirst",
        entry_date=datetime(2026, 5, 22).date(),
    )
    module.append_ledger(
        ledger,
        "## Daily Pilot Metrics\n\nnext",
        entry_date=datetime(2026, 5, 23).date(),
    )

    result = ledger.read_text(encoding="utf-8")
    assert result.count("## 自动导出记录") == 1
    assert "pilot-metrics:2026-05-22:begin" in result
    assert "pilot-metrics:2026-05-23:begin" in result


def _load_export_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts/export-daily-pilot-metrics.py"
    spec = importlib.util.spec_from_file_location("export_daily_pilot_metrics", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
