from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.models import AuditLog, TDL


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "diagnose-pilot-calendar-gaps.py"
SPEC = importlib.util.spec_from_file_location("diagnose_pilot_calendar_gaps", SCRIPT_PATH)
assert SPEC is not None
SCRIPT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SCRIPT
SPEC.loader.exec_module(SCRIPT)


def _tdl() -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title="完成招生复盘",
        owner_id="owner-1",
        due_at=datetime(2026, 5, 22, 18, 0, tzinfo=UTC),
        status="active",
        source="dingtalk_msg",
        created_by="owner-1",
    )


def _audit(action: str, error: str | None = None) -> AuditLog:
    return AuditLog(
        entity_type="tdl",
        entity_id="tdl-1",
        action=action,
        actor_id="owner-1",
        payload={"error": error} if error else {},
    )


def test_classify_calendar_gap_detects_missing_app_scope() -> None:
    gap = SCRIPT.classify_calendar_gap(
        _tdl(),
        [_audit("calendar_create_failed", "应用尚未开通所需的权限：[qyapi_calendar_create]")],
    )

    assert gap.reason == "app_calendar_scope_missing_at_attempt"
    assert gap.latest_calendar_action == "calendar_create_failed"


def test_classify_calendar_gap_detects_missing_user_authorization() -> None:
    gap = SCRIPT.classify_calendar_gap(_tdl(), [_audit("calendar_authorization_required")])

    assert gap.reason == "missing_user_authorization"


def test_classify_calendar_gap_defaults_to_no_attempt() -> None:
    gap = SCRIPT.classify_calendar_gap(_tdl(), [])

    assert gap.reason == "no_calendar_attempt"


def test_render_calendar_gaps_outputs_markdown_table() -> None:
    gap = SCRIPT.classify_calendar_gap(_tdl(), [])

    result = SCRIPT.render_calendar_gaps([gap])

    assert "# Pilot Calendar Gaps" in result
    assert "Missing calendar events: 1" in result
    assert "| no_calendar_attempt | active | owner-1 |" in result
