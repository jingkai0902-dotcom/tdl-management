from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntakeQueueItem
from app.schemas import DingTalkIncomingMessage


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
RECEIVED = "received"
PROCESSING = "processing"
DONE = "done"
FAILED = "failed"
DEFAULT_PROCESSING_STALE_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class EnqueueResult:
    item: IntakeQueueItem
    created: bool


async def enqueue_intake_message(
    session: AsyncSession,
    message: DingTalkIncomingMessage,
) -> EnqueueResult:
    existing = await get_intake_by_message_id(session, message.message_id)
    if existing is not None:
        return EnqueueResult(existing, created=False)

    item = IntakeQueueItem(
        message_id=message.message_id,
        sender_id=message.sender_id,
        sender_nick=message.sender_nick,
        content=message.content,
        status=RECEIVED,
    )
    session.add(item)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_intake_by_message_id(session, message.message_id)
        if existing is None:
            raise
        return EnqueueResult(existing, created=False)
    await session.refresh(item)
    return EnqueueResult(item, created=True)


async def get_intake_by_message_id(
    session: AsyncSession,
    message_id: str,
) -> IntakeQueueItem | None:
    result = await session.execute(
        select(IntakeQueueItem).where(IntakeQueueItem.message_id == message_id)
    )
    return result.scalar_one_or_none()


async def claim_next_intake(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    processing_stale_after: timedelta = DEFAULT_PROCESSING_STALE_AFTER,
) -> IntakeQueueItem | None:
    claimed_at = as_of or datetime.now(SHANGHAI_TZ)
    stale_cutoff = claimed_at - processing_stale_after
    result = await session.execute(
        select(IntakeQueueItem)
        .where(
            or_(
                IntakeQueueItem.status.in_([RECEIVED, FAILED]),
                and_(
                    IntakeQueueItem.status == PROCESSING,
                    or_(
                        IntakeQueueItem.locked_at.is_(None),
                        IntakeQueueItem.locked_at < stale_cutoff,
                    ),
                ),
            )
        )
        .where(IntakeQueueItem.attempts < IntakeQueueItem.max_attempts)
        .order_by(IntakeQueueItem.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    item.status = PROCESSING
    item.attempts += 1
    item.locked_at = claimed_at
    item.last_error = None
    await session.commit()
    await session.refresh(item)
    return item


async def mark_intake_done(
    session: AsyncSession,
    item: IntakeQueueItem,
    *,
    as_of: datetime | None = None,
) -> IntakeQueueItem:
    item.status = DONE
    item.processed_at = as_of or datetime.now(SHANGHAI_TZ)
    item.last_error = None
    await session.commit()
    await session.refresh(item)
    return item


async def mark_intake_failed(
    session: AsyncSession,
    item: IntakeQueueItem,
    *,
    error: Exception | str,
) -> IntakeQueueItem:
    item.status = FAILED
    item.last_error = str(error)[:4000]
    await session.commit()
    await session.refresh(item)
    return item
