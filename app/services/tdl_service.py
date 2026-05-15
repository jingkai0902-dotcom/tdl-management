from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, TDL
from app.schemas import TDLCreate, TDLDraftCreate, TDLDraftUpdate


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


async def list_tdls(session: AsyncSession) -> list[TDL]:
    result = await session.execute(select(TDL).order_by(TDL.created_at.desc()))
    return list(result.scalars().all())
