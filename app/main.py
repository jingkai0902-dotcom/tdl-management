from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.tdl_crud import router as tdl_router
from app.config import get_settings


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(tdl_router)
