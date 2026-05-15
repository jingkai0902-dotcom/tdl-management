from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TDL(Base):
    __tablename__ = "tdls"

    tdl_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID | None] = mapped_column(ForeignKey("meetings.meeting_id"))
    decision_id: Mapped[UUID | None] = mapped_column(ForeignKey("decisions.decision_id"))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("tdls.tdl_id"))

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(128))
    participants: Mapped[list[str]] = mapped_column(JSONB, default=list)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(32), default="draft")
    priority: Mapped[str] = mapped_column(String(16), default="P2")
    business_line: Mapped[str | None] = mapped_column(String(64))
    function_domain: Mapped[str | None] = mapped_column(String(64))
    product_line: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(32))
    key_actions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)

    waiting_for: Mapped[list[str]] = mapped_column(JSONB, default=list)
    blocked_by: Mapped[list[str]] = mapped_column(JSONB, default=list)
    completion_criteria: Mapped[str | None] = mapped_column(Text)
    linked_goal: Mapped[str | None] = mapped_column(Text)
    outcome_kpi: Mapped[str | None] = mapped_column(Text)
    roi_estimate: Mapped[str | None] = mapped_column(String(16))

    source: Mapped[str] = mapped_column(String(64), default="manual")
    calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    decision = relationship("Decision", back_populates="tdls")
