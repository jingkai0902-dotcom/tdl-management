from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.dingtalk_client import DingTalkClient
from app.models import AuditLog, TDL


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