from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import WeeklyReportRead
from app.services.review_service import generate_weekly_report


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/weekly", response_model=WeeklyReportRead)
async def get_weekly_report_endpoint(
    period_start: datetime,
    period_end: datetime,
    as_of: datetime,
    session: AsyncSession = Depends(get_session),
) -> WeeklyReportRead:
    if period_end <= period_start:
        raise HTTPException(status_code=400, detail="period_end must be after period_start")
    return await generate_weekly_report(
        session,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
    )
