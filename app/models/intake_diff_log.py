from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IntakeDiffLog(Base):
    __tablename__ = "intake_diff_logs"

    diff_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tdl_id: Mapped[UUID | None] = mapped_column(ForeignKey("tdls.tdl_id"), index=True)
    message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), index=True)
    draft_payload: Mapped[dict | None] = mapped_column(JSONB)
    confirmed_payload: Mapped[dict | None] = mapped_column(JSONB)
    diff_fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
