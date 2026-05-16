"""calendar authorizations

Revision ID: 0002_calendar_authorizations
Revises: 0001_initial_schema
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_calendar_authorizations"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_authorizations",
        sa.Column("dingtalk_user_id", sa.String(length=128), primary_key=True),
        sa.Column("union_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("scope", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("calendar_authorizations")
