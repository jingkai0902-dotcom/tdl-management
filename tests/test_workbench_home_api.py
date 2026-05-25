import pytest

from app.api.workbench_home import get_workbench_home_view


@pytest.mark.asyncio
async def test_get_workbench_home_view_renders_unified_read_only_prototype() -> None:
    response = await get_workbench_home_view()
    body = response.body.decode()

    assert response.status_code == 200
    assert "企业工作台" in body
    assert "V0 只读首页原型" in body
    assert "不创建任务" in body
    assert "不修改状态" in body
    assert "不发布报告" in body
    assert "TDL 任务数据与 5 月月会人工判断样本" in body
    assert "行动与目标" in body
    assert "经营数据" in body
    assert "议题与线索" in body
    assert "资料与报告" in body
    assert "月度重点 / 部门计划" in body
    assert "季度目标 / 关键项目" in body
    assert "年度目标 / 里程碑" in body


@pytest.mark.asyncio
async def test_get_workbench_home_view_only_reuses_read_endpoints_and_disables_future_actions() -> None:
    response = await get_workbench_home_view()
    body = response.body.decode()

    assert "新建任务" in body
    assert "记录议题" in body
    assert "补充想法" in body
    assert "尚未开放" in body
    assert "规划中" in body
    assert "<button class=\"tool-button\" disabled>" in body
    assert "fetch(`/workbench?${taskParams.toString()}`)" in body
    assert 'fetch("/workbench/meeting-review")' in body
    assert "不会直接生成任务" in body
    assert 'const priority = ["pending_confirmation", "overdue_or_due_soon", "today", "this_week", "in_progress"]' in body
    assert "item-list" in body
    assert "展开完整内容" in body
    assert "item.title.length > 110" in body
    assert "method:" not in body
