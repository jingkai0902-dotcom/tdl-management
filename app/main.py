from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.calendar_auth import router as calendar_auth_router
from app.api.dingtalk_webhook import router as dingtalk_router
from app.api.entry import router as entry_router
from app.api.health import router as health_router
from app.api.meetings import router as meetings_router
from app.api.reminders import router as reminders_router
from app.api.reports import router as reports_router
from app.api.tdl_crud import router as tdl_router
from app.api.workbench import router as workbench_router
from app.api.workbench_meeting_review import router as workbench_meeting_review_router
from app.config import get_settings
from app.workers.scheduler import build_scheduler


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(entry_router)
app.include_router(health_router)
app.include_router(calendar_auth_router)
app.include_router(tdl_router)
app.include_router(dingtalk_router)
app.include_router(meetings_router)
app.include_router(reminders_router)
app.include_router(reports_router)
if settings.workbench_v0_enabled:
    app.include_router(workbench_router)
    app.include_router(workbench_meeting_review_router)
