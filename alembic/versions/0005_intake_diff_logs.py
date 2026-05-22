"""Add intake diff logs.

Revision ID: 0005_intake_diff_logs
Revises: 0004_intake_queue
Create Date: 2026-05-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_intake_diff_logs"
down_revision: str | None = "0004_intake_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intake_diff_logs",
        sa.Column("diff_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tdl_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tdls.tdl_id"), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("draft_payload", postgresql.JSONB(), nullable=True),
        sa.Column("confirmed_payload", postgresql.JSONB(), nullable=True),
        sa.Column("diff_fields", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_intake_diff_logs_tdl_id", "intake_diff_logs", ["tdl_id"])
    op.create_index("ix_intake_diff_logs_message_id", "intake_diff_logs", ["message_id"])
    op.create_index("ix_intake_diff_logs_action_type", "intake_diff_logs", ["action_type"])
    op.create_index("ix_intake_diff_logs_actor_id", "intake_diff_logs", ["actor_id"])


def downgrade() -> None:
    op.drop_index("ix_intake_diff_logs_actor_id", table_name="intake_diff_logs")
    op.drop_index("ix_intake_diff_logs_action_type", table_name="intake_diff_logs")
    op.drop_index("ix_intake_diff_logs_message_id", table_name="intake_diff_logs")
    op.drop_index("ix_intake_diff_logs_tdl_id", table_name="intake_diff_logs")
    op.drop_table("intake_diff_logs")
