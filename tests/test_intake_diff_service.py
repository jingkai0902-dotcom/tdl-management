from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models import IntakeDiffLog, TDL
from app.schemas import TDLDraftCreate, TDLDraftUpdate
from app.services.intake_diff_service import diff_field_names, tdl_payload
from app.services.tdl_service import create_draft_tdl, update_draft_tdl


class FakeSession:
    def __init__(self, *tdls: TDL) -> None:
        self.tdls = {tdl.tdl_id: tdl for tdl in tdls}
        self.items = []

    def add(self, item) -> None:
        self.items.append(item)
        if isinstance(item, TDL):
            self.tdls[item.tdl_id] = item

    async def flush(self) -> None:
        for item in self.items:
            for attr in ("tdl_id", "audit_id", "diff_id"):
                if hasattr(item, attr) and getattr(item, attr) is None:
                    setattr(item, attr, uuid4())

    async def commit(self) -> None:
        return None

    async def refresh(self, item) -> None:
        return None

    async def get(self, model, identifier):
        return self.tdls.get(identifier)


def test_diff_field_names_compares_payloads() -> None:
    assert diff_field_names(
        {"owner_id": None, "due_at": None, "priority": "P2"},
        {"owner_id": "user-1", "due_at": None, "priority": "P2"},
    ) == ["owner_id"]


def test_tdl_payload_serializes_datetime() -> None:
    due_at = datetime(2026, 5, 22, 18, 0, tzinfo=UTC)
    tdl = TDL(
        tdl_id=uuid4(),
        title="审核暑期班方案",
        owner_id="user-1",
        due_at=due_at,
        completion_criteria=None,
        priority="P1",
        created_by="user-1",
        source="dingtalk_msg",
        status="draft",
    )

    assert tdl_payload(tdl)["due_at"] == due_at.isoformat()


@pytest.mark.asyncio
async def test_create_draft_tdl_records_initial_intake_diff_log() -> None:
    session = FakeSession()

    draft = await create_draft_tdl(
        session,
        TDLDraftCreate(
            title="审核暑期班方案",
            owner_id=None,
            due_at=None,
            created_by="user-1",
            source="dingtalk_msg",
            raw_text="下周三前审核暑期班方案",
            priority="P2",
            confidence=0.9,
        ),
    )

    diff_logs = [item for item in session.items if isinstance(item, IntakeDiffLog)]

    assert len(diff_logs) == 1
    assert diff_logs[0].tdl_id == draft.tdl_id
    assert diff_logs[0].action_type == "draft_created"
    assert diff_logs[0].source == "dingtalk_msg"
    assert diff_logs[0].raw_text == "下周三前审核暑期班方案"
    assert diff_logs[0].confirmed_payload["title"] == "审核暑期班方案"


@pytest.mark.asyncio
async def test_update_draft_tdl_records_changed_fields() -> None:
    due_at = datetime(2026, 5, 22, 18, 0, tzinfo=UTC)
    draft = TDL(
        tdl_id=uuid4(),
        title="审核暑期班方案",
        owner_id=None,
        due_at=None,
        completion_criteria=None,
        priority="P2",
        created_by="user-1",
        source="dingtalk_msg",
        status="draft",
    )
    session = FakeSession(draft)

    await update_draft_tdl(
        session,
        draft.tdl_id,
        TDLDraftUpdate(owner_id="user-1", due_at=due_at),
        "user-1",
    )

    diff_logs = [item for item in session.items if isinstance(item, IntakeDiffLog)]

    assert len(diff_logs) == 1
    assert diff_logs[0].action_type == "draft_updated"
    assert diff_logs[0].diff_fields == ["due_at", "owner_id"]
    assert diff_logs[0].draft_payload["owner_id"] is None
    assert diff_logs[0].confirmed_payload["owner_id"] == "user-1"
    assert diff_logs[0].confirmed_payload["due_at"] == due_at.isoformat()
