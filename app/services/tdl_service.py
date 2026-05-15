from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, TDL
from app.schemas import TDLCreate


async def create_tdl(session: AsyncSession, payload: TDLCreate) -> TDL:
    tdl = TDL(**payload.model_dump())
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


async def list_tdls(session: AsyncSession) -> list[TDL]:
    result = await session.execute(select(TDL).order_by(TDL.created_at.desc()))
    return list(result.scalars().all())
