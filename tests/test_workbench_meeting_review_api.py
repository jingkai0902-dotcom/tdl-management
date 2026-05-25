import pytest

from app.api.workbench_meeting_review import (
    get_meeting_review_endpoint,
    get_meeting_review_view,
)


@pytest.mark.asyncio
async def test_get_meeting_review_endpoint_reads_real_business_gold_set() -> None:
    payload = await get_meeting_review_endpoint()

    assert payload.total_count == 32
    assert payload.sections[0].items[0].summary == "公司薪资多维表格已完成首次试运行"


@pytest.mark.asyncio
async def test_get_meeting_review_view_states_read_only_and_task_gate_boundary() -> None:
    response = await get_meeting_review_view()
    body = response.body.decode()

    assert response.status_code == 200
    assert "励步 5 月月会判断样本" in body
    assert "不创建任务、不修改状态、不发送通知" in body
    assert "不可直接转为任务" in body
    assert "不能把“待议题、火花、观察线索”误当作待办任务" in body
    assert "/workbench/home/view" in body
    assert 'fetch("/workbench/meeting-review")' in body
