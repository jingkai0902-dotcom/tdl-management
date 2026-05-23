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


def test_cleanup_allowlist_contains_ten_unique_stale_attention_items() -> None:
    module = _load_script()

    ids = [candidate.tdl_id for candidate in module.STALE_ATTENTION_CANDIDATES]
    titles = [candidate.title for candidate in module.STALE_ATTENTION_CANDIDATES]

    assert len(ids) == 10
    assert len(set(ids)) == 10
    assert "前往钻石校区教授Claude使用方法" in titles
    assert "核验薪资规则，确认三条异常" in titles
    assert "处理家长投诉" in titles


def test_cleanup_categories_do_not_overlap() -> None:
    module = _load_script()

    test_ids = {candidate.tdl_id for candidate in module.TEST_RESIDUAL_CANDIDATES}
    stale_ids = {candidate.tdl_id for candidate in module.STALE_ATTENTION_CANDIDATES}

    assert test_ids.isdisjoint(stale_ids)


def test_cleanup_script_defaults_to_dry_run() -> None:
    module = _load_script()

    args = module.parse_args([])

    assert args.execute is False
    assert args.category == "test-residual"


def test_cleanup_script_accepts_stale_attention_category() -> None:
    module = _load_script()

    args = module.parse_args(["--category", "stale-attention"])

    assert args.category == "stale-attention"
    assert args.execute is False


def test_cleanup_script_execute_flag_is_explicit() -> None:
    module = _load_script()

    args = module.parse_args(["--execute"])

    assert args.execute is True
