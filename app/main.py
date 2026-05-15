from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dingtalk_webhook import router as dingtalk_router
from app.api.health import router as health_router
from app.api.meetings import router as meetings_router
from app.api.reminders import router as reminders_router
from app.api.reports import router as reports_router
from app.api.tdl_crud import router as tdl_router
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
app.include_router(health_router)
app.include_router(tdl_router)
app.include_router(dingtalk_router)
app.include_router(meetings_router)
app.include_router(reminders_router)
app.include_router(reports_router)
