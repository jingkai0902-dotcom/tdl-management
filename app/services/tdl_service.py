from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, TDL
from app.schemas import BatchConfirmDraftsRead, TDLCreate, TDLDraftCreate, TDLDraftUpdate, TDLRead


ACTIONABLE_STATUSES = {"active", "attention", "snoozed"}


async def create_tdl(session: AsyncSession, payload: TDLCreate) -> TDL:
    tdl = TDL(**payload.model_dump(), status="active")
    session.add(tdl)
    await session.flush()

    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="create",
            actor_id=payload.created_by,
            payload=payload.model_dump(mode="json"),
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def create_draft_tdl(session: AsyncSession, payload: TDLDraftCreate) -> TDL:
    data = payload.model_dump(exclude={"raw_text"})
    data["status"] = "draft"
    tdl = TDL(**data)
    session.add(tdl)
    await session.flush()

    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="draft_create",
            actor_id=payload.created_by,
            payload=payload.model_dump(mode="json"),
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def confirm_tdl(session: AsyncSession, tdl_id, actor_id: str) -> TDL:
    tdl = await session.get(TDL, tdl_id)
    if tdl is None:
        raise ValueError("TDL not found")
    missing_fields = [
        field_name
        for field_name in ("owner_id", "due_at")
        if getattr(tdl, field_name) is None
    ]
    if missing_fields:
        raise ValueError(f"TDL draft missing required fields: {', '.join(missing_fields)}")
    tdl.status = "active"
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="confirm",
            actor_id=actor_id,
            payload={},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def update_draft_tdl(
    session: AsyncSession,
    tdl_id,
    payload: TDLDraftUpdate,
    actor_id: str,
) -> TDL:
    tdl = await session.get(TDL, tdl_id)
    if tdl is None:
        raise ValueError("TDL not found")
    if tdl.status != "draft":
        raise ValueError("Only draft TDLs can be updated through draft completion")

    updates = payload.model_dump(exclude_none=True)
    for field_name, value in updates.items():
        setattr(tdl, field_name, value)

    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="draft_update",
            actor_id=actor_id,
            payload=payload.model_dump(mode="json", exclude_none=True),
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def confirm_ready_drafts(
    session: AsyncSession,
    tdl_ids: list,
    actor_id: str,
) -> BatchConfirmDraftsRead:
    confirmed_entities = []
    skipped = []

    for tdl_id in tdl_ids:
        tdl = await session.get(TDL, tdl_id)
        if tdl is None:
            continue
        tdl_read = TDLRead.from_tdl(tdl)
        if tdl.status != "draft" or tdl_read.missing_fields:
            skipped.append(tdl_read)
            continue
        tdl.status = "active"
        session.add(
            AuditLog(
                entity_type="tdl",
                entity_id=str(tdl.tdl_id),
                action="confirm",
                actor_id=actor_id,
                payload={"batch": True},
            )
        )
        confirmed_entities.append(tdl)

    await session.commit()
    for tdl in confirmed_entities:
        await session.refresh(tdl)

    return BatchConfirmDraftsRead(
        confirmed=[TDLRead.from_tdl(tdl) for tdl in confirmed_entities],
        skipped=skipped,
    )


async def complete_tdl(session: AsyncSession, tdl_id, actor_id: str) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    tdl.status = "done"
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="complete",
            actor_id=actor_id,
            payload={},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def postpone_tdl(
    session: AsyncSession,
    tdl_id,
    *,
    due_at: datetime,
    actor_id: str,
) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    previous_due_at = tdl.due_at
    tdl.due_at = due_at
    if tdl.status == "snoozed":
        tdl.status = "active"
        tdl.snooze_until = None
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="postpone",
            actor_id=actor_id,
            payload={
                "previous_due_at": previous_due_at.isoformat() if previous_due_at else None,
                "due_at": due_at.isoformat(),
            },
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def snooze_tdl(
    session: AsyncSession,
    tdl_id,
    *,
    snooze_until: datetime,
    actor_id: str,
) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    tdl.status = "snoozed"
    tdl.snooze_until = snooze_until
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="snooze",
            actor_id=actor_id,
            payload={"snooze_until": snooze_until.isoformat()},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def request_help_tdl(session: AsyncSession, tdl_id, actor_id: str) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    tdl.status = "attention"
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="need_help",
            actor_id=actor_id,
            payload={},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def _get_actionable_tdl(session: AsyncSession, tdl_id) -> TDL:
    tdl = await session.get(TDL, tdl_id)
    if tdl is None:
        raise ValueError("TDL not found")
    if tdl.status not in ACTIONABLE_STATUSES:
        raise ValueError("Only open TDLs can receive lifecycle actions")
    return tdl


async def list_tdls(session: AsyncSession) -> list[TDL]:
    result = await session.execute(select(TDL).order_by(TDL.created_at.desc()))
    return list(result.scalars().all())
