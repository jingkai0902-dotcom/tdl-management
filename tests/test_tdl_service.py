from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models import TDL
from app.schemas import TDLDraftUpdate
from app.services.tdl_service import (
    complete_tdl,
    confirm_ready_drafts,
    confirm_tdl,
    postpone_tdl,
    snooze_tdl,
    update_draft_tdl,
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


def _draft_tdl(*, owner_id=None, due_at=None) -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title="排定新师培训课表",
        owner_id=owner_id,
        due_at=due_at,
        priority="P2",
        created_by="0617564550-1513038363",
        source="meeting_minutes",
        status="draft",
    )


def _active_tdl(*, due_at=None) -> TDL:
    return TDL(
        tdl_id=uuid4(),
        title="推进市场 SOP",
        owner_id="0617564550-1513038363",
        due_at=due_at,
        priority="P2",
        created_by="0617564550-1513038363",
        source="manual",
        status="active",
    )


def test_tdl_read_next_actions_follow_missing_fields() -> None:
    from app.schemas import TDLRead

    incomplete = TDLRead.from_tdl(_draft_tdl())
    complete = TDLRead.from_tdl(
        _draft_tdl(
            owner_id="0617564550-1513038363",
            due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
        )
    )

    assert incomplete.next_actions == ["set_owner", "set_due_at"]
    assert incomplete.recommended_fields == ["completion_criteria"]
    assert incomplete.recommended_actions == ["set_completion_criteria"]
    assert complete.next_actions == ["confirm"]
    assert complete.recommended_fields == ["completion_criteria"]
    assert complete.recommended_actions == ["set_completion_criteria"]


@pytest.mark.asyncio
async def test_confirm_tdl_rejects_incomplete_draft() -> None:
    tdl = _draft_tdl()
    session = FakeSession(tdl)

    with pytest.raises(ValueError, match="owner_id, due_at"):
        await confirm_tdl(session, tdl.tdl_id, "0617564550-1513038363")

    assert tdl.status == "draft"


@pytest.mark.asyncio
async def test_update_draft_tdl_fills_missing_fields_before_confirm() -> None:
    tdl = _draft_tdl()
    session = FakeSession(tdl)
    due_at = datetime(2026, 5, 31, 18, 0, tzinfo=UTC)

    await update_draft_tdl(
        session,
        tdl.tdl_id,
        TDLDraftUpdate(
            owner_id="0617564550-1513038363",
            due_at=due_at,
        ),
        "0617564550-1513038363",
    )
    confirmed = await confirm_tdl(session, tdl.tdl_id, "0617564550-1513038363")

    assert confirmed.owner_id == "0617564550-1513038363"
    assert confirmed.due_at == due_at
    assert confirmed.status == "active"


@pytest.mark.asyncio
async def test_confirm_ready_drafts_only_confirms_complete_items() -> None:
    complete = _draft_tdl(
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
    )
    incomplete = _draft_tdl(owner_id="0617564550-1513038363")
    session = FakeSession(complete, incomplete)

    result = await confirm_ready_drafts(
        session,
        [complete.tdl_id, incomplete.tdl_id],
        "0617564550-1513038363",
    )

    assert [tdl.tdl_id for tdl in result.confirmed] == [complete.tdl_id]
    assert [tdl.tdl_id for tdl in result.skipped] == [incomplete.tdl_id]
    assert complete.status == "active"
    assert incomplete.status == "draft"


@pytest.mark.asyncio
async def test_complete_tdl_marks_done_and_writes_audit() -> None:
    tdl = _active_tdl()
    session = FakeSession(tdl)

    completed = await complete_tdl(session, tdl.tdl_id, "0617564550-1513038363")

    assert completed.status == "done"
    assert session.items[-1].action == "complete"


@pytest.mark.asyncio
async def test_postpone_tdl_updates_due_at_and_writes_audit() -> None:
    original_due_at = datetime(2026, 5, 20, 18, 0, tzinfo=UTC)
    new_due_at = datetime(2026, 5, 22, 18, 0, tzinfo=UTC)
    tdl = _active_tdl(due_at=original_due_at)
    session = FakeSession(tdl)

    postponed = await postpone_tdl(
        session,
        tdl.tdl_id,
        due_at=new_due_at,
        actor_id="0617564550-1513038363",
    )

    assert postponed.due_at == new_due_at
    assert session.items[-1].action == "postpone"
    assert session.items[-1].payload == {
        "previous_due_at": original_due_at.isoformat(),
        "due_at": new_due_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_postpone_tdl_reactivates_snoozed_task() -> None:
    tdl = _active_tdl(due_at=datetime(2026, 5, 20, 18, 0, tzinfo=UTC))
    tdl.status = "snoozed"
    tdl.snooze_until = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
    session = FakeSession(tdl)

    postponed = await postpone_tdl(
        session,
        tdl.tdl_id,
        due_at=datetime(2026, 5, 22, 18, 0, tzinfo=UTC),
        actor_id="0617564550-1513038363",
    )

    assert postponed.status == "active"
    assert postponed.snooze_until is None


@pytest.mark.asyncio
async def test_snooze_tdl_sets_resume_time_without_changing_due_date() -> None:
    due_at = datetime(2026, 5, 20, 18, 0, tzinfo=UTC)
    snooze_until = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
    tdl = _active_tdl(due_at=due_at)
    session = FakeSession(tdl)

    snoozed = await snooze_tdl(
        session,
        tdl.tdl_id,
        snooze_until=snooze_until,
        actor_id="0617564550-1513038363",
    )

    assert snoozed.status == "snoozed"
    assert snoozed.snooze_until == snooze_until
    assert snoozed.due_at == due_at
    assert session.items[-1].action == "snooze"


@pytest.mark.asyncio
async def test_lifecycle_actions_reject_drafts() -> None:
    tdl = _draft_tdl(
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
    )
    session = FakeSession(tdl)

    with pytest.raises(ValueError, match="Only open TDLs"):
        await complete_tdl(session, tdl.tdl_id, "0617564550-1513038363")
