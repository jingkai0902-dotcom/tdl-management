from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.ai_client import AIClient, get_ai_client
from app.models import AuditLog, Decision, Meeting, TDL
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


async def parse_meeting_minutes(
    session: AsyncSession,
    payload: MeetingMinutesIngest,
    ai_client: AIClient | None = None,
) -> tuple[Meeting, list[Decision], list[TDL]]:
    client = ai_client or get_ai_client()
    meeting = Meeting(
        title=payload.title,
        source_text=payload.source_text,
        participants=[],
    )
    session.add(meeting)
    await session.flush()

    try:
        decision_drafts = await client.extract_meeting_decisions(payload.source_text)
    except Exception:
        await session.rollback()
        raise

    decisions: list[Decision] = []
    tdls: list[TDL] = []
    for draft in decision_drafts:
        decision = Decision(
            meeting_id=meeting.meeting_id,
            title=draft.title,
            owner_id=draft.owner_id,
            completion_criteria=draft.completion_criteria,
        )
        session.add(decision)
        await session.flush()
        decisions.append(decision)

        tdl = TDL(
            meeting_id=meeting.meeting_id,
            decision_id=decision.decision_id,
            title=draft.tdl_title,
            owner_id=draft.owner_id,
            due_at=draft.due_at,
            completion_criteria=draft.completion_criteria,
            created_by=payload.created_by,
            source="meeting_minutes",
            status="draft",
        )
        session.add(tdl)
        await session.flush()
        tdls.append(tdl)

    session.add(
        AuditLog(
            entity_type="meeting",
            entity_id=str(meeting.meeting_id),
            action="parse_minutes",
            actor_id=payload.created_by,
            payload={"decision_count": len(decisions), "tdl_count": len(tdls)},
        )
    )
    await session.commit()
    await session.refresh(meeting)
    return meeting, decisions, tdls


async def get_meeting_results(
    session: AsyncSession,
    meeting_id,
) -> tuple[Meeting, list[Decision], list[TDL]]:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise ValueError("Meeting not found")

    decisions_result = await session.execute(
        select(Decision).where(Decision.meeting_id == meeting_id).order_by(Decision.created_at.asc())
    )
    tdls_result = await session.execute(
        select(TDL).where(TDL.meeting_id == meeting_id).order_by(TDL.created_at.asc())
    )
    return meeting, list(decisions_result.scalars().all()), list(tdls_result.scalars().all())
