from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models import TDL
from app.services.workbench_service import build_workbench_summary, generate_workbench_summary


def _tdl(
    *,
    title: str,
    status: str,
    due_at: datetime | None,
    owner_id: str = "owner-1",
) -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title=title,
        owner_id=owner_id,
        due_at=due_at,
        status=status,
        priority="P2",
        source="manual",
        created_by="owner-1",
        created_at=datetime(2026, 5, 24, 8, 0, tzinfo=UTC),
    )


def _section_counts(summary):
    return {section.key: section.count for section in summary.sections}


def _section_titles(summary, key: str) -> list[str]:
    for section in summary.sections:
        if section.key == key:
            return [item.title for item in section.items]
    raise AssertionError(f"section not found: {key}")


def test_build_workbench_summary_groups_v0_sections() -> None:
    as_of = datetime(2026, 5, 24, 9, 0, tzinfo=UTC)
    today = _tdl(
        title="今天完成续费名单",
        status="active",
        due_at=datetime(2026, 5, 24, 18, 0, tzinfo=UTC),
    )
    overdue = _tdl(
        title="昨天补齐招生复盘",
        status="attention",
        due_at=datetime(2026, 5, 23, 18, 0, tzinfo=UTC),
    )
    next_week = _tdl(
        title="下周准备月会材料",
        status="active",
        due_at=datetime(2026, 5, 26, 18, 0, tzinfo=UTC),
    )
    draft = _tdl(
        title="待确认暑期班安排",
        status="draft",
        due_at=None,
    )
    done = _tdl(
        title="已完成事项不进打开项",
        status="done",
        due_at=as_of + timedelta(hours=1),
    )

    summary = build_workbench_summary(
        [today, overdue, next_week, draft, done],
        as_of=as_of,
    )

    assert _section_counts(summary) == {
        "today": 1,
        "this_week": 1,
        "overdue_or_due_soon": 2,
        "in_progress": 3,
        "pending_confirmation": 1,
    }
    assert _section_titles(summary, "today") == ["今天完成续费名单"]
    assert _section_titles(summary, "pending_confirmation") == ["待确认暑期班安排"]
    assert [section.title for section in summary.sections if section.key == "this_week"] == ["本周剩余"]


def test_build_workbench_summary_keeps_data_source_visible() -> None:
    summary = build_workbench_summary(
        [],
        as_of=datetime(2026, 5, 24, 9, 0, tzinfo=UTC),
    )

    assert summary.data_source == "tdls"
    assert all(section.data_source == "tdls" for section in summary.sections)


def test_build_workbench_summary_formats_management_owner_name() -> None:
    summary = build_workbench_summary(
        [
            _tdl(
                title="Helen 负责的任务",
                status="active",
                due_at=datetime(2026, 5, 24, 18, 0, tzinfo=UTC),
                owner_id="0611436746849471",
            )
        ],
        as_of=datetime(2026, 5, 24, 9, 0, tzinfo=UTC),
    )

    assert summary.sections[0].items[0].owner_label == "李珍 / Helen"


class FakeResult:
    def __init__(self, tdls):
        self._tdls = tdls

    def scalars(self):
        return self

    def all(self):
        return self._tdls


class FakeSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return FakeResult([])


@pytest.mark.asyncio
async def test_generate_workbench_summary_filters_owner_id() -> None:
    session = FakeSession()

    await generate_workbench_summary(
        session,
        as_of=datetime(2026, 5, 24, 9, 0, tzinfo=UTC),
        owner_id="owner-1",
    )

    assert "tdls.owner_id = :owner_id_1" in str(session.statement)
