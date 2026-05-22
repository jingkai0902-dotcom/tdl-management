from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models import IntakeQueueItem
from app.services.intake_queue_service import (
    PROCESSING,
    claim_next_intake,
    mark_intake_failed,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class FakeScalarResult:
    def __init__(self, item):
        self.item = item

    def scalar_one_or_none(self):
        return self.item


class FakeSession:
    def __init__(self, item=None) -> None:
        self.item = item
        self.statements = []
        self.commits = 0
        self.refreshed = []

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeScalarResult(self.item)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, item) -> None:
        self.refreshed.append(item)


def _queue_item(*, status: str = "received", locked_at=None, attempts: int = 0) -> IntakeQueueItem:
    return IntakeQueueItem(
        intake_id=uuid4(),
        message_id=str(uuid4()),
        sender_id="user-1",
        content="下周三前审核暑期班方案",
        status=status,
        locked_at=locked_at,
        attempts=attempts,
        max_attempts=3,
    )


@pytest.mark.asyncio
async def test_claim_next_intake_reclaims_stale_processing_item() -> None:
    now = datetime(2026, 5, 22, 9, 30, tzinfo=SHANGHAI_TZ)
    item = _queue_item(
        status=PROCESSING,
        locked_at=now - timedelta(minutes=30),
        attempts=1,
    )
    session = FakeSession(item)

    claimed = await claim_next_intake(
        session,
        as_of=now,
        processing_stale_after=timedelta(minutes=10),
    )

    assert claimed is item
    assert item.status == PROCESSING
    assert item.attempts == 2
    assert item.locked_at == now
    assert session.commits == 1
    assert session.refreshed == [item]


@pytest.mark.asyncio
async def test_claim_next_intake_marks_failed_item_processing_for_retry() -> None:
    now = datetime(2026, 5, 22, 9, 30, tzinfo=SHANGHAI_TZ)
    item = _queue_item(status="failed", attempts=1)
    session = FakeSession(item)

    claimed = await claim_next_intake(session, as_of=now)

    assert claimed is item
    assert item.status == PROCESSING
    assert item.attempts == 2
    assert item.locked_at == now
    assert item.last_error is None


@pytest.mark.asyncio
async def test_mark_intake_failed_preserves_row_for_retry_until_max_attempts() -> None:
    item = _queue_item(status=PROCESSING, attempts=2)
    session = FakeSession(item)

    failed = await mark_intake_failed(session, item, error="provider down")

    assert failed.status == "failed"
    assert failed.attempts == 2
    assert failed.last_error == "provider down"
    assert session.commits == 1
