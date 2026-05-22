from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.config import load_yaml_config
from app.integrations.dingtalk_card import build_draft_card
from app.schemas import (
    DecisionRead,
    MeetingMinutesIngest,
    MeetingOwnerGroupRead,
    MeetingParseRead,
    TDLCardRead,
    TDLRead,
)
from app.services.meeting_service import (
    create_meeting_from_minutes,
    get_meeting_results,
    parse_meeting_minutes,
)


router = APIRouter(prefix="/meetings", tags=["meetings"])


PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


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
        owner_groups=_build_owner_groups(tdl_reads),
    )


def _build_owner_groups(tdls: list[TDLRead]) -> list[MeetingOwnerGroupRead]:
    grouped: dict[str | None, list[TDLRead]] = {}
    for tdl in tdls:
        grouped.setdefault(tdl.owner_id, []).append(tdl)

    groups = []
    for owner_id, owner_tdls in grouped.items():
        sorted_tdls = sorted(
            owner_tdls,
            key=lambda tdl: (
                PRIORITY_RANK.get(tdl.priority, 99),
                tdl.due_at is None,
                tdl.due_at or "",
                tdl.title,
            ),
        )
        ready_count = sum(1 for tdl in sorted_tdls if not tdl.missing_fields)
        groups.append(
            MeetingOwnerGroupRead(
                owner_id=owner_id,
                owner_label=_owner_label(owner_id),
                tdl_count=len(sorted_tdls),
                ready_to_confirm_count=ready_count,
                incomplete_count=len(sorted_tdls) - ready_count,
                tdls=sorted_tdls,
            )
        )
    return sorted(groups, key=lambda group: (group.owner_id is None, group.owner_label))


def _owner_label(owner_id: str | None) -> str:
    if owner_id is None:
        return "[待补负责人]"
    roster = load_yaml_config("management_roster.yaml")
    for member in roster.get("management", []):
        if str(member.get("dingtalk_user_id")) != owner_id:
            continue
        name = member.get("name")
        english_name = member.get("english_name")
        if name and english_name:
            return f"{name} / {english_name}"
        if name:
            return str(name)
    return owner_id


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
