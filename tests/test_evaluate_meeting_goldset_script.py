import argparse
import importlib.util
from pathlib import Path


def _script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts/evaluate-meeting-goldset.py"
    spec = importlib.util.spec_from_file_location("evaluate_meeting_goldset", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _report(**summary_overrides):
    summary = {
        "gate_violation_count": 0,
        "false_confirmed_count": 0,
        "fabricated_date_count": 0,
        "deep_processing_error_count": 0,
    }
    summary.update(summary_overrides)
    return {"summary": summary}


def _args(**overrides):
    values = {
        "fail_on_gate_violations": False,
        "fail_on_false_confirmed": False,
        "fail_on_fabricated_dates": False,
        "fail_on_deep_processing_errors": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_eval_script_keeps_default_exit_code_zero_for_bad_report() -> None:
    module = _script_module()

    assert module._exit_code_for_report(
        _report(gate_violation_count=1, false_confirmed_count=1),
        _args(),
    ) == 0


def test_eval_script_can_fail_on_gate_violations() -> None:
    module = _script_module()

    assert module._exit_code_for_report(
        _report(gate_violation_count=1),
        _args(fail_on_gate_violations=True),
    ) == 1


def test_eval_script_can_fail_on_critical_safety_counts() -> None:
    module = _script_module()

    assert module._exit_code_for_report(
        _report(false_confirmed_count=1),
        _args(fail_on_false_confirmed=True),
    ) == 1
    assert module._exit_code_for_report(
        _report(fabricated_date_count=1),
        _args(fail_on_fabricated_dates=True),
    ) == 1
    assert module._exit_code_for_report(
        _report(deep_processing_error_count=1),
        _args(fail_on_deep_processing_errors=True),
    ) == 1
