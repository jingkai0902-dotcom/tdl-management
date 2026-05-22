import argparse
import importlib.util
from pathlib import Path


def _script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts/export-meeting-model-predictions.py"
    spec = importlib.util.spec_from_file_location("export_meeting_model_predictions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _args(**overrides):
    values = {
        "fail_on_gate_violations": False,
        "fail_on_false_confirmed": False,
        "fail_on_fabricated_dates": False,
        "fail_on_deep_processing_errors": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _report(**summary_overrides):
    summary = {
        "gate_violation_count": 0,
        "false_confirmed_count": 0,
        "fabricated_date_count": 0,
        "deep_processing_error_count": 0,
    }
    summary.update(summary_overrides)
    return {"summary": summary}


def test_export_script_detects_strict_eval_flags() -> None:
    module = _script_module()

    assert module._has_strict_eval_flags(_args()) is False
    assert module._has_strict_eval_flags(_args(fail_on_gate_violations=True)) is True


def test_export_script_strict_eval_failure_matches_enabled_flags() -> None:
    module = _script_module()

    assert module._strict_eval_failed(
        _report(gate_violation_count=1),
        _args(),
    ) is False
    assert module._strict_eval_failed(
        _report(gate_violation_count=1),
        _args(fail_on_gate_violations=True),
    ) is True
    assert module._strict_eval_failed(
        _report(false_confirmed_count=1),
        _args(fail_on_false_confirmed=True),
    ) is True
    assert module._strict_eval_failed(
        _report(fabricated_date_count=1),
        _args(fail_on_fabricated_dates=True),
    ) is True
    assert module._strict_eval_failed(
        _report(deep_processing_error_count=1),
        _args(fail_on_deep_processing_errors=True),
    ) is True
