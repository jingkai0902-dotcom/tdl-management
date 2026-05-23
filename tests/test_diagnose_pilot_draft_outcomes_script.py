from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys
from uuid import uuid4

from app.models import AuditLog, IntakeDiffLog, TDL


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "diagnose-pilot-draft-outcomes.py"
SPEC = importlib.util.spec_from_file_location("diagnose_pilot_draft_outcomes", SCRIPT_PATH)
assert SPEC is not None
SCRIPT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SCRIPT
SPEC.loader.exec_module(SCRIPT)


def _tdl(
    *,
    tdl_id,
    title: str = "审核暑期班方案",
    status: str = "draft",
    owner_id: str | None = None,
    due_at: datetime | None = None,
    completion_criteria: str | None = None,
) -> TDL:
    return TDL(
        tdl_id=tdl_id,
        title=title,
        owner_id=owner_id,
        due_at=due_at,
        status=status,
        source="dingtalk_msg",
        created_by="owner-1",
        created_at=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
        completion_criteria=completion_criteria,
    )


def _diff(*, tdl_id, action_type: str, raw_text: str | None = None) -> IntakeDiffLog:
    return IntakeDiffLog(
        tdl_id=tdl_id,
        message_id=str(uuid4()),
        raw_text=raw_text,
        action_type=action_type,
        source="dingtalk_msg",
        actor_id="owner-1",
        draft_payload=None,
        confirmed_payload={},
        diff_fields=[],
        created_at=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
    )


def _audit(*, tdl_id, action: str) -> AuditLog:
    return AuditLog(
        entity_type="tdl",
        entity_id=str(tdl_id),
        action=action,
        actor_id="owner-1",
        payload={},
        created_at=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
    )


def test_build_draft_outcomes_classifies_confirmed_and_canceled() -> None:
    confirmed_id = uuid4()
    canceled_id = uuid4()

    outcomes = SCRIPT.build_draft_outcomes(
        [
            _tdl(
                tdl_id=confirmed_id,
                status="active",
                owner_id="owner-1",
                due_at=datetime(2026, 5, 23, 18, tzinfo=UTC),
                completion_criteria="形成一页结论",
            ),
            _tdl(tdl_id=canceled_id, status="canceled"),
        ],
        [
            _diff(tdl_id=confirmed_id, action_type="draft_created", raw_text="明天审核方案"),
            _diff(tdl_id=confirmed_id, action_type="confirmed"),
            _diff(tdl_id=canceled_id, action_type="draft_created", raw_text="先不用建"),
            _diff(tdl_id=canceled_id, action_type="canceled"),
        ],
        [],
    )

    by_id = {item.tdl_id: item for item in outcomes}
    assert by_id[str(confirmed_id)].outcome == "confirmed"
    assert by_id[str(confirmed_id)].missing_fields == ()
    assert by_id[str(canceled_id)].outcome == "canceled"
    assert by_id[str(canceled_id)].missing_fields == (
        "owner_id",
        "due_at",
        "completion_criteria",
    )


def test_build_draft_outcomes_classifies_confirmed_then_canceled() -> None:
    tdl_id = uuid4()

    outcomes = SCRIPT.build_draft_outcomes(
        [
            _tdl(
                tdl_id=tdl_id,
                status="canceled",
                owner_id="owner-1",
                due_at=datetime(2026, 5, 23, 18, tzinfo=UTC),
            )
        ],
        [
            _diff(tdl_id=tdl_id, action_type="draft_created"),
            _diff(tdl_id=tdl_id, action_type="confirmed"),
        ],
        [],
    )

    assert outcomes[0].outcome == "confirmed_then_canceled"


def test_build_draft_outcomes_falls_back_to_audit_logs() -> None:
    tdl_id = uuid4()

    outcomes = SCRIPT.build_draft_outcomes(
        [_tdl(tdl_id=tdl_id, status="canceled")],
        [],
        [
            _audit(tdl_id=tdl_id, action="draft_create"),
            _audit(tdl_id=tdl_id, action="cancel"),
        ],
    )

    assert len(outcomes) == 1
    assert outcomes[0].outcome == "canceled"
    assert outcomes[0].actions == ("draft_create", "cancel")


def test_render_draft_outcomes_outputs_summary_and_table() -> None:
    tdl_id = uuid4()
    outcomes = SCRIPT.build_draft_outcomes(
        [_tdl(tdl_id=tdl_id, status="draft")],
        [_diff(tdl_id=tdl_id, action_type="draft_created", raw_text="明天审核方案")],
        [],
    )

    result = SCRIPT.render_draft_outcomes(outcomes)

    assert "# Pilot Draft Outcome Diagnosis" in result
    assert "Drafts sampled: 1" in result
    assert "still_draft 1" in result
    assert str(tdl_id) in result
    assert "owner_id" in result
    assert "Cancel reason" in result
    assert "明天审核方案" in result
