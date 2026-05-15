"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("meeting_type", sa.String(length=64), nullable=False),
        sa.Column("held_at", sa.DateTime(timezone=True)),
        sa.Column("source_text", sa.Text()),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("participants", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "decisions",
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meetings.meeting_id"), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner_id", sa.String(length=128)),
        sa.Column("completion_criteria", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tdls",
        sa.Column("tdl_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meetings.meeting_id")),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("decisions.decision_id")),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tdls.tdl_id")),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("participants", postgresql.JSONB(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("snooze_until", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("business_line", sa.String(length=64)),
        sa.Column("function_domain", sa.String(length=64)),
        sa.Column("product_line", sa.String(length=64)),
        sa.Column("stage", sa.String(length=32)),
        sa.Column("key_actions", postgresql.JSONB(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("waiting_for", postgresql.JSONB(), nullable=False),
        sa.Column("blocked_by", postgresql.JSONB(), nullable=False),
        sa.Column("completion_criteria", sa.Text()),
        sa.Column("linked_goal", sa.Text()),
        sa.Column("outcome_kpi", sa.Text()),
        sa.Column("roi_estimate", sa.String(length=16)),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("calendar_event_id", sa.String(length=255)),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128)),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("tdls")
    op.drop_table("decisions")
    op.drop_table("meetings")
