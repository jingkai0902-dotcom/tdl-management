from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Meeting
from app.schemas import MeetingMinutesIngest


async def create_meeting_from_minutes(
    session: AsyncSession,
    payload: MeetingMinutesIngest,
) -> Meeting:
    meeting = Meeting(
        title=payload.title,
        source_text=payload.source_text,
        participants=[],
    )
    session.add(meeting)
    await session.flush()
    session.add(
        AuditLog(
            entity_type="meeting",
            entity_id=str(meeting.meeting_id),
            action="ingest_minutes",
            actor_id=payload.created_by,
            payload={"title": payload.title},
        )
    )
    await session.commit()
    await session.refresh(meeting)
    return meeting
