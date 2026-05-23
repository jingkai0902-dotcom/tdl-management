import importlib.util
from pathlib import Path
import sys


def _load_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "cleanup-pilot-attention-backlog.py"
    spec = importlib.util.spec_from_file_location("cleanup_pilot_attention_backlog", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cleanup_allowlist_contains_eight_unique_test_residuals() -> None:
    module = _load_script()

    ids = [candidate.tdl_id for candidate in module.TEST_RESIDUAL_CANDIDATES]
    titles = [candidate.title for candidate in module.TEST_RESIDUAL_CANDIDATES]

    assert len(ids) == 8
    assert len(set(ids)) == 8
    assert "日历同步联调测试" in titles
    assert "将姓名更正为李珍（珍珠的珍），即 Helen" in titles
    assert "完成 Codex 草稿模板卡 D1 复测" in titles


def test_cleanup_script_defaults_to_dry_run() -> None:
    module = _load_script()

    args = module.parse_args([])

    assert args.execute is False


def test_cleanup_script_execute_flag_is_explicit() -> None:
    module = _load_script()

    args = module.parse_args(["--execute"])

    assert args.execute is True
