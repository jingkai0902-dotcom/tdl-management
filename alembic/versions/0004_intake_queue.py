"""Add intake queue.

Revision ID: 0004_intake_queue
Revises: 0003_tdl_cancel_reason
Create Date: 2026-05-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_intake_queue"
down_revision: str | None = "0003_tdl_cancel_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intake_queue",
        sa.Column("intake_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("sender_id", sa.String(length=128), nullable=False),
        sa.Column("sender_nick", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("message_id", name="uq_intake_queue_message_id"),
    )
    op.create_index("ix_intake_queue_sender_id", "intake_queue", ["sender_id"])
    op.create_index("ix_intake_queue_status", "intake_queue", ["status"])


def downgrade() -> None:
    op.drop_index("ix_intake_queue_status", table_name="intake_queue")
    op.drop_index("ix_intake_queue_sender_id", table_name="intake_queue")
    op.drop_table("intake_queue")
