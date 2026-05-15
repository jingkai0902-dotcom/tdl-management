from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import TDLCreate, TDLRead
from app.services.calendar_service import create_tdl_with_calendar
from app.services.tdl_service import list_tdls


router = APIRouter(prefix="/tdls", tags=["tdls"])


@router.post("", response_model=TDLRead, status_code=status.HTTP_201_CREATED)
async def create_tdl_endpoint(
    payload: TDLCreate,
    session: AsyncSession = Depends(get_session),
) -> TDLRead:
    return await create_tdl_with_calendar(session, payload)


@router.get("", response_model=list[TDLRead])
async def list_tdls_endpoint(session: AsyncSession = Depends(get_session)) -> list[TDLRead]:
    return await list_tdls(session)