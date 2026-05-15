from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models import TDL
from app.services.reminder_service import (
    build_reminder_candidates,
    build_sendable_reminder_cards,
    mark_attention_tdls,
    run_reminder_cycle,
)


class FakeSession:
    def __init__(self, *tdls: TDL) -> None:
        self.tdls = {tdl.tdl_id: tdl for tdl in tdls}
        self.items = []

    async def get(self, model, identifier):
        return self.tdls.get(identifier)

    def add(self, item) -> None:
        self.items.append(item)

    async def commit(self) -> None:
        return None

    async def refresh(self, item) -> None:
        return None

    async def execute(self, statement):
        return FakeResult(list(self.tdls.values()))


class FakeResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


def _tdl(
    *,
    due_at: datetime | None,
    owner_id: str | None = "owner-1",
    status: str = "active",
    snooze_until: datetime | None = None,
) -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title="测试任务",
        owner_id=owner_id,
        due_at=due_at,
        snooze_until=snooze_until,
        status=status,
        priority="P2",
        created_by="owner-1",
        source="manual",
    )


def test_build_reminder_candidates_routes_by_overdue_days() -> None:
    as_of = datetime(2026, 5, 18, 8, 30, tzinfo=UTC)
    due_today = _tdl(due_at=datetime(2026, 5, 18, 18, 0, tzinfo=UTC))
    overdue_1 = _tdl(due_at=datetime(2026, 5, 17, 18, 0, tzinfo=UTC))
    overdue_2 = _tdl(due_at=datetime(2026, 5, 16, 18, 0, tzinfo=UTC))
    overdue_3 = _tdl(due_at=datetime(2026, 5, 15, 18, 0, tzinfo=UTC))

    candidates = build_reminder_candidates(
        [due_today, overdue_1, overdue_2, overdue_3],
        as_of=as_of,
        policy={
            "overdue_day_1": "remind_owner",
            "overdue_day_2": "ask_owner",
            "overdue_day_3": "mark_attention",
        },
    )

    assert [candidate.action for candidate in candidates] == [
        "due_today",
        "remind_owner",
        "ask_owner",
        "mark_attention",
    ]
    assert [candidate.overdue_days for candidate in candidates] == [0, 1, 2, 3]


def test_build_reminder_candidates_skips_future_snoozed_and_incomplete_items() -> None:
    as_of = datetime(2026, 5, 18, 8, 30, tzinfo=UTC)
    future = _tdl(due_at=datetime(2026, 5, 19, 18, 0, tzinfo=UTC))
    snoozed = _tdl(
        due_at=datetime(2026, 5, 17, 18, 0, tzinfo=UTC),
        snooze_until=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )
    missing_owner = _tdl(
        due_at=datetime(2026, 5, 17, 18, 0, tzinfo=UTC),
        owner_id=None,
    )
    draft = _tdl(
        due_at=datetime(2026, 5, 17, 18, 0, tzinfo=UTC),
        status="draft",
    )

    assert build_reminder_candidates(
        [future, snoozed, missing_owner, draft],
        as_of=as_of,
        policy={
            "overdue_day_1": "remind_owner",
            "overdue_day_2": "ask_owner",
            "overdue_day_3": "mark_attention",
        },
    ) == []


@pytest.mark.asyncio
async def test_mark_attention_tdls_updates_status_and_writes_audit() -> None:
    tdl = _tdl(due_at=datetime(2026, 5, 15, 18, 0, tzinfo=UTC))
    session = FakeSession(tdl)
    candidate = build_reminder_candidates(
        [tdl],
        as_of=datetime(2026, 5, 18, 8, 30, tzinfo=UTC),
        policy={"overdue_day_3": "mark_attention"},
    )[0]

    marked = await mark_attention_tdls(session, [candidate])

    assert [item.tdl_id for item in marked] == [tdl.tdl_id]
    assert tdl.status == "attention"
    assert session.items[-1].action == "mark_attention"


def test_build_sendable_reminder_cards_skips_mark_attention_candidates() -> None:
    due_today = _tdl(due_at=datetime(2026, 5, 18, 18, 0, tzinfo=UTC))
    day_two = _tdl(due_at=datetime(2026, 5, 16, 18, 0, tzinfo=UTC))
    day_three = _tdl(due_at=datetime(2026, 5, 15, 18, 0, tzinfo=UTC))
    candidates = build_reminder_candidates(
        [due_today, day_two, day_three],
        as_of=datetime(2026, 5, 18, 8, 30, tzinfo=UTC),
        policy={
            "overdue_day_2": "ask_owner",
            "overdue_day_3": "mark_attention",
        },
    )

    dispatches = build_sendable_reminder_cards([due_today, day_two, day_three], candidates)

    assert [dispatch.card.title for dispatch in dispatches] == ["今日待办", "需要支持"]
    assert [dispatch.owner_id for dispatch in dispatches] == ["owner-1", "owner-1"]


@pytest.mark.asyncio
async def test_run_reminder_cycle_returns_dispatches_and_marks_attention() -> None:
    due_today = _tdl(due_at=datetime(2026, 5, 18, 18, 0, tzinfo=UTC))
    day_three = _tdl(due_at=datetime(2026, 5, 15, 18, 0, tzinfo=UTC))
    session = FakeSession(due_today, day_three)

    result = await run_reminder_cycle(
        session,
        as_of=datetime(2026, 5, 18, 8, 30, tzinfo=UTC),
    )

    assert result.candidate_count == 2
    assert result.marked_attention_count == 1
    assert [dispatch.card.title for dispatch in result.dispatches] == ["今日待办"]
    assert day_three.status == "attention"
