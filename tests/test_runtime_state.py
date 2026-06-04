from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.runtime_state import (
    runtime_state_path,
    summarize_error,
    write_failure,
    write_heartbeat,
    write_started,
    write_success,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_state_writes_heartbeat_with_stable_fields(tmp_path: Path) -> None:
    now = datetime(2026, 5, 31, 10, 0, tzinfo=SHANGHAI_TZ)

    assert write_heartbeat(
        "intake_worker",
        state_dir=tmp_path,
        now=now,
        pid=123,
        best_effort=False,
    )

    payload = _read_state(tmp_path / "intake_worker.state.json")
    assert payload["schema_version"] == 1
    assert payload["process_name"] == "intake_worker"
    assert payload["pid"] == 123
    assert payload["started_at"] == now.isoformat()
    assert payload["last_heartbeat_at"] == now.isoformat()
    assert payload["processed_count"] == 0
    assert payload["current_mode"] == "healthy"
    assert payload["stop_signal"] is None


def test_runtime_state_success_preserves_started_at_and_increments_count(tmp_path: Path) -> None:
    started_at = datetime(2026, 5, 31, 10, 0, tzinfo=SHANGHAI_TZ)
    success_at = datetime(2026, 5, 31, 10, 3, tzinfo=SHANGHAI_TZ)

    write_started("intake_worker", state_dir=tmp_path, now=started_at, pid=123, best_effort=False)
    write_success(
        "intake_worker",
        state_dir=tmp_path,
        now=success_at,
        pid=123,
        processed_increment=2,
        best_effort=False,
    )

    payload = _read_state(tmp_path / "intake_worker.state.json")
    assert payload["started_at"] == started_at.isoformat()
    assert payload["last_started_at"] == started_at.isoformat()
    assert payload["last_success_at"] == success_at.isoformat()
    assert payload["processed_count"] == 2
    assert payload["last_error"] is None
    assert payload["current_mode"] == "healthy"


def test_runtime_state_failure_redacts_and_truncates_error(tmp_path: Path) -> None:
    failed_at = datetime(2026, 5, 31, 10, 5, tzinfo=SHANGHAI_TZ)
    error = RuntimeError("access_token=abc123 " + ("x" * 800))

    write_failure(
        "scheduler/reminders",
        error,
        state_dir=tmp_path,
        now=failed_at,
        pid=456,
        stop_signal="reminder_job_failed",
        best_effort=False,
    )

    path = tmp_path / "scheduler_reminders.state.json"
    payload = _read_state(path)
    assert payload["process_name"] == "scheduler/reminders"
    assert payload["pid"] == 456
    assert payload["last_error_at"] == failed_at.isoformat()
    assert "abc123" not in payload["last_error"]
    assert "access_token=[REDACTED]" in payload["last_error"]
    assert len(payload["last_error"]) <= 500
    assert payload["current_mode"] == "degraded"
    assert payload["stop_signal"] == "reminder_job_failed"


def test_runtime_state_path_rejects_empty_process_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="process_name"):
        runtime_state_path("///", state_dir=tmp_path)


def test_runtime_state_best_effort_swallows_write_errors(monkeypatch, tmp_path: Path) -> None:
    def fail_replace(*args, **kwargs):
        raise OSError("disk is read-only")

    monkeypatch.setattr("app.runtime_state.os.replace", fail_replace)

    assert not write_heartbeat("backend", state_dir=tmp_path)


def test_summarize_error_redacts_common_secret_assignments() -> None:
    summary = summarize_error(
        "password=hunter2 refresh_token:tok123 api-key=key456 normal text",
        limit=200,
    )
    assert "hunter2" not in summary
    assert "tok123" not in summary
    assert "key456" not in summary
    assert "normal text" in summary


def test_summarize_error_redacts_camel_case_and_bearer_secrets() -> None:
    summary = summarize_error(
        "accessToken=dt-token apiKey=sk-key Authorization: Bearer sk-live-token normal text",
        limit=300,
    )

    assert "dt-token" not in summary
    assert "sk-key" not in summary
    assert "sk-live-token" not in summary
    assert "accessToken=[REDACTED]" in summary
    assert "apiKey=[REDACTED]" in summary
    assert "Authorization: Bearer [REDACTED]" in summary
    assert "normal text" in summary
