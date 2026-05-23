from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from app.models import TDL


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare-button-validation-card.py"
SPEC = importlib.util.spec_from_file_location("prepare_button_validation_card", SCRIPT_PATH)
assert SPEC is not None
SCRIPT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SCRIPT
SPEC.loader.exec_module(SCRIPT)


def test_scenario_for_d4_owner_creates_missing_owner_draft() -> None:
    scenario = SCRIPT.scenario_for("d4-owner", actor_id="frank-id")

    assert scenario.status == "draft"
    assert scenario.owner_id is None
    assert scenario.due_at is not None
    assert scenario.card_kind == "draft"
    assert "补负责人" in scenario.title
    assert "不要点击按钮" in scenario.instruction
    assert "负责人改成李珍" in scenario.instruction


def test_scenario_for_a4_non_owner_targets_helen_but_sends_to_actor() -> None:
    scenario = SCRIPT.scenario_for("a4-non-owner", actor_id="frank-id")

    assert scenario.status == "active"
    assert scenario.owner_id == "0611436746849471"
    assert scenario.card_kind == "created"
    assert "非owner" in scenario.title


def test_parse_args_defaults_to_dry_run_for_prepare() -> None:
    args = SCRIPT._parse_args(["--scenario", "a5-complete", "--run-id", "run-1"])

    assert args.scenario == "a5-complete"
    assert args.run_id == "run-1"
    assert args.send is False


def test_parse_args_defaults_to_dry_run_for_cleanup() -> None:
    args = SCRIPT._parse_args(["--cleanup-run-id", "run-1"])

    assert args.cleanup_run_id == "run-1"
    assert args.execute_cleanup is False


def test_parse_args_requires_explicit_cleanup_execute_flag() -> None:
    args = SCRIPT._parse_args(["--cleanup-run-id", "run-1", "--execute-cleanup"])

    assert args.execute_cleanup is True


@pytest.mark.asyncio
async def test_create_validation_tdl_marks_source_as_button_validation(monkeypatch) -> None:
    added = []

    class FakeSession:
        def add(self, item):
            added.append(item)

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, item):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(SCRIPT, "SessionLocal", lambda: FakeSession())

    scenario = SCRIPT.scenario_for("d5-due", actor_id="frank-id")
    tdl = await SCRIPT._create_validation_tdl(
        scenario,
        actor_id="frank-id",
        run_id="run-1",
    )

    assert tdl.source == SCRIPT.VALIDATION_SOURCE
    assert any(isinstance(item, TDL) and item.source == SCRIPT.VALIDATION_SOURCE for item in added)
