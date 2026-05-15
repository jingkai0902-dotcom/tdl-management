from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import ReminderRunRead
from app.services.reminder_service import run_reminder_cycle


router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("/run", response_model=ReminderRunRead)
async def run_reminder_cycle_endpoint(
    as_of: datetime,
    session: AsyncSession = Depends(get_session),
) -> ReminderRunRead:
    return await run_reminder_cycle(session, as_of=as_of)
