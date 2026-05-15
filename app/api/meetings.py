from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.integrations.dingtalk_card import build_draft_card
from app.schemas import DecisionRead, MeetingMinutesIngest, MeetingParseRead, TDLCardRead, TDLRead
from app.services.meeting_service import (
    create_meeting_from_minutes,
    get_meeting_results,
    parse_meeting_minutes,
)


router = APIRouter(prefix="/meetings", tags=["meetings"])


def _build_meeting_parse_read(meeting, decisions, tdls) -> MeetingParseRead:
    tdl_reads = [TDLRead.from_tdl(tdl) for tdl in tdls]
    ready_to_confirm_tdls = [tdl for tdl in tdl_reads if not tdl.missing_fields]
    incomplete_tdls = [tdl for tdl in tdl_reads if tdl.missing_fields]
    return MeetingParseRead(
        meeting_id=meeting.meeting_id,
        decision_count=len(decisions),
        tdl_count=len(tdls),
        ready_to_confirm_count=len(ready_to_confirm_tdls),
        incomplete_count=len(incomplete_tdls),
        decisions=[DecisionRead.model_validate(decision) for decision in decisions],
        tdls=tdl_reads,
        ready_to_confirm_tdls=ready_to_confirm_tdls,
        incomplete_tdls=incomplete_tdls,
        draft_cards=[TDLCardRead.model_validate(build_draft_card(tdl)) for tdl in tdls],
    )


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
    return _build_meeting_parse_read(meeting, decisions, tdls)


@router.get("/{meeting_id}/results")
async def get_meeting_results_endpoint(
    meeting_id,
    session: AsyncSession = Depends(get_session),
) -> MeetingParseRead:
    try:
        meeting, decisions, tdls = await get_meeting_results(session, meeting_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_meeting_parse_read(meeting, decisions, tdls)
