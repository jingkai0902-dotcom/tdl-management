from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.integrations.dingtalk_card import build_draft_card
from app.schemas import DecisionRead, MeetingMinutesIngest, MeetingParseRead, TDLCardRead, TDLRead
from app.services.meeting_service import create_meeting_from_minutes, parse_meeting_minutes


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


@router.post("/parse", status_code=status.HTTP_201_CREATED)
async def parse_meeting_minutes_endpoint(
    payload: MeetingMinutesIngest,
    session: AsyncSession = Depends(get_session),
) -> MeetingParseRead:
    meeting, decisions, tdls = await parse_meeting_minutes(session, payload)
    tdl_reads = [TDLRead.from_tdl(tdl) for tdl in tdls]
    return MeetingParseRead(
        meeting_id=meeting.meeting_id,
        decision_count=len(decisions),
        tdl_count=len(tdls),
        ready_to_confirm_count=sum(not tdl.missing_fields for tdl in tdl_reads),
        incomplete_count=sum(bool(tdl.missing_fields) for tdl in tdl_reads),
        decisions=[DecisionRead.model_validate(decision) for decision in decisions],
        tdls=tdl_reads,
        draft_cards=[TDLCardRead.model_validate(build_draft_card(tdl)) for tdl in tdls],
    )
