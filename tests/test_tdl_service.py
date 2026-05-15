from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models import TDL
from app.schemas import TDLDraftUpdate
from app.services.tdl_service import confirm_tdl, update_draft_tdl


class FakeSession:
    def __init__(self, tdl: TDL) -> None:
        self.tdl = tdl
        self.items = []

    async def get(self, model, identifier):
        if identifier == self.tdl.tdl_id:
            return self.tdl
        return None

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
    assert complete.next_actions == ["confirm"]


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
