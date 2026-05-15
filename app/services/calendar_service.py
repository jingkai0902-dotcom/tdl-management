from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.dingtalk_client import DingTalkAPIError, DingTalkClient
from app.models import AuditLog, TDL
from app.schemas import BatchConfirmDraftsRead, TDLCreate
from app.services.tdl_service import (
    confirm_ready_drafts,
    confirm_tdl,
    create_tdl,
    postpone_tdl,
)


def _calendar_duration_minutes() -> int:
    calendar = load_yaml_config("dingtalk_config.yaml").get("calendar", {})
    return int(calendar.get("default_duration_minutes", 30))


def _calendar_description(tdl: TDL) -> str:
    return f"TDL ID: {tdl.tdl_id}"


def should_create_calendar_event(tdl: TDL) -> bool:
    return (
        tdl.status == "active"
        and tdl.owner_id is not None
        and tdl.due_at is not None
        and tdl.calendar_event_id is None
    )


def should_update_calendar_event(tdl: TDL) -> bool:
    return (
        tdl.status == "active"
        and tdl.owner_id is not None
        and tdl.due_at is not None
        and tdl.calendar_event_id is not None
    )


async def create_calendar_event_for_tdl(
    session: AsyncSession,
    tdl: TDL,
    *,
    actor_id: str,
    client: DingTalkClient | None = None,
) -> TDL:
    if not should_create_calendar_event(tdl):
        return tdl

    dingtalk_client = client or DingTalkClient()
    event_id = await dingtalk_client.create_tdl_calendar_event(
        owner_id=tdl.owner_id,
        title=tdl.title,
        due_at=tdl.due_at,
        participant_user_ids=tdl.participants,
        description=_calendar_description(tdl),
        duration_minutes=_calendar_duration_minutes(),
    )
    tdl.calendar_event_id = event_id
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="calendar_create",
            actor_id=actor_id,
            payload={"calendar_event_id": event_id},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def update_calendar_event_for_tdl(
    session: AsyncSession,
    tdl: TDL,
    *,
    actor_id: str,
    client: DingTalkClient | None = None,
) -> TDL:
    if not should_update_calendar_event(tdl):
        return tdl

    dingtalk_client = client or DingTalkClient()
    await dingtalk_client.update_tdl_calendar_event(
        event_id=tdl.calendar_event_id,
        owner_id=tdl.owner_id,
        title=tdl.title,
        due_at=tdl.due_at,
        participant_user_ids=tdl.participants,
        description=_calendar_description(tdl),
        duration_minutes=_calendar_duration_minutes(),
    )
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="calendar_update",
            actor_id=actor_id,
            payload={"calendar_event_id": tdl.calendar_event_id},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def sync_calendar_event_best_effort(
    session: AsyncSession,
    tdl: TDL,
    *,
    actor_id: str,
    client: DingTalkClient | None = None,
) -> TDL:
    try:
        return await create_calendar_event_for_tdl(
            session,
            tdl,
            actor_id=actor_id,
            client=client,
        )
    except DingTalkAPIError as exc:
        session.add(
            AuditLog(
                entity_type="tdl",
                entity_id=str(tdl.tdl_id),
                action="calendar_create_failed",
                actor_id=actor_id,
                payload={"error": str(exc)},
            )
        )
        await session.commit()
        await session.refresh(tdl)
        return tdl


async def sync_calendar_due_at_change_best_effort(
    session: AsyncSession,
    tdl: TDL,
    *,
    actor_id: str,
    client: DingTalkClient | None = None,
) -> TDL:
    if tdl.calendar_event_id is None:
        return await sync_calendar_event_best_effort(
            session,
            tdl,
            actor_id=actor_id,
            client=client,
        )
    try:
        return await update_calendar_event_for_tdl(
            session,
            tdl,
            actor_id=actor_id,
            client=client,
        )
    except DingTalkAPIError as exc:
        session.add(
            AuditLog(
                entity_type="tdl",
                entity_id=str(tdl.tdl_id),
                action="calendar_update_failed",
                actor_id=actor_id,
                payload={"error": str(exc)},
            )
        )
        await session.commit()
        await session.refresh(tdl)
        return tdl


async def create_tdl_with_calendar(
    session: AsyncSession,
    payload: TDLCreate,
    *,
    client: DingTalkClient | None = None,
) -> TDL:
    tdl = await create_tdl(session, payload)
    return await sync_calendar_event_best_effort(
        session,
        tdl,
        actor_id=payload.created_by,
        client=client,
    )


async def confirm_tdl_with_calendar(
    session: AsyncSession,
    tdl_id,
    actor_id: str,
    *,
    client: DingTalkClient | None = None,
) -> TDL:
    tdl = await confirm_tdl(session, tdl_id, actor_id)
    return await sync_calendar_event_best_effort(
        session,
        tdl,
        actor_id=actor_id,
        client=client,
    )


async def confirm_ready_drafts_with_calendar(
    session: AsyncSession,
    tdl_ids: list,
    actor_id: str,
    *,
    client: DingTalkClient | None = None,
) -> BatchConfirmDraftsRead:
    result = await confirm_ready_drafts(session, tdl_ids, actor_id)
    for confirmed_tdl in result.confirmed:
        tdl = await session.get(TDL, confirmed_tdl.tdl_id)
        if tdl is None:
            continue
        await sync_calendar_event_best_effort(
            session,
            tdl,
            actor_id=actor_id,
            client=client,
        )
    return result


async def postpone_tdl_with_calendar(
    session: AsyncSession,
    tdl_id,
    *,
    due_at,
    actor_id: str,
    client: DingTalkClient | None = None,
) -> TDL:
    tdl = await postpone_tdl(
        session,
        tdl_id,
        due_at=due_at,
        actor_id=actor_id,
    )
    return await sync_calendar_due_at_change_best_effort(
        session,
        tdl,
        actor_id=actor_id,
        client=client,
    )