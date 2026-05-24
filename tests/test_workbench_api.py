from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.api.workbench import get_workbench_endpoint, get_workbench_view
from app.schemas import WorkbenchRead, WorkbenchSectionRead


@pytest.mark.asyncio
async def test_get_workbench_endpoint_returns_summary(monkeypatch) -> None:
    as_of = datetime(2026, 5, 24, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    async def fake_generate_workbench_summary(session, *, as_of, owner_id=None):
        assert session is None
        assert as_of == datetime(2026, 5, 24, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert owner_id is None
        return WorkbenchRead(
            as_of=as_of,
            data_source="tdls",
            sections=[
                WorkbenchSectionRead(
                    key="today",
                    title="今日",
                    count=0,
                    data_source="tdls",
                    items=[],
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.workbench.generate_workbench_summary",
        fake_generate_workbench_summary,
    )

    result = await get_workbench_endpoint(as_of=as_of, session=None)

    assert result.as_of == as_of
    assert result.sections[0].key == "today"


@pytest.mark.asyncio
async def test_get_workbench_endpoint_defaults_naive_as_of_to_scheduler_timezone(monkeypatch) -> None:
    async def fake_generate_workbench_summary(session, *, as_of, owner_id=None):
        assert as_of == datetime(2026, 5, 24, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert owner_id == "owner-1"
        return WorkbenchRead(as_of=as_of, data_source="tdls", sections=[])

    monkeypatch.setattr(
        "app.api.workbench.generate_workbench_summary",
        fake_generate_workbench_summary,
    )

    result = await get_workbench_endpoint(
        as_of=datetime(2026, 5, 24, 9, 0),
        owner_id="owner-1",
        session=None,
    )

    assert result.as_of.tzinfo == ZoneInfo("Asia/Shanghai")


@pytest.mark.asyncio
async def test_get_workbench_endpoint_converts_utc_as_of_to_scheduler_timezone(monkeypatch) -> None:
    async def fake_generate_workbench_summary(session, *, as_of, owner_id=None):
        assert as_of == datetime(2026, 5, 24, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        return WorkbenchRead(as_of=as_of, data_source="tdls", sections=[])

    monkeypatch.setattr(
        "app.api.workbench.generate_workbench_summary",
        fake_generate_workbench_summary,
    )

    result = await get_workbench_endpoint(
        as_of=datetime(2026, 5, 24, 0, 30, tzinfo=UTC),
        session=None,
    )

    assert result.as_of.tzinfo == ZoneInfo("Asia/Shanghai")


@pytest.mark.asyncio
async def test_get_workbench_view_renders_read_only_shell() -> None:
    response = await get_workbench_view()
    body = response.body.decode()

    assert response.status_code == 200
    assert "TDL 管理工作台 V0" in body
    assert "只读视图" in body
    assert "fetch(`/workbench?${params.toString()}`)" in body
    assert "不创建任务" in body
    assert "不修改状态" in body
    assert "同一任务可能同时出现在多个区块" in body
    assert "/workbench/view?owner_id=0617564550-1513038363" in body
    assert "/workbench/view?owner_id=0611436746849471" in body
    assert "params.set(\"owner_id\", ownerId)" in body
    assert "escapeHtml(item.title)" in body
    assert "item.owner_label || item.owner_id" in body
    assert "任务详情" in body
    assert "只读详情" in body
    assert "data-tdl-id" in body
    assert "renderDetail(item)" in body
    assert "补负责人" in body
    assert "补截止时间" in body
    assert "补完成标准" in body
    assert "满足确认条件" in body
    assert "completion_criteria: \"完成标准\"" in body
