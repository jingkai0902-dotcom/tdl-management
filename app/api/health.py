from fastapi import APIRouter
from sqlalchemy import text

from app.database import engine


router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}
