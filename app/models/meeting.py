from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    meeting_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    meeting_type: Mapped[str] = mapped_column(String(64), default="monthly_review")
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_text: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    decisions = relationship("Decision", back_populates="meeting", cascade="all, delete-orphan")
