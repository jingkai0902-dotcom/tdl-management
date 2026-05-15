from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import MeetingMinutesIngest
from app.services.meeting_service import create_meeting_from_minutes


router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_meeting_minutes(
    payload: MeetingMinutesIngest,
    session: AsyncSession = Depends(get_session),
):
    meeting = await create_meeting_from_minutes(session, payload)
    return {
        "meeting_id": meeting.meeting_id,
        "title": meeting.title,
        "status": "ingested",
    }
