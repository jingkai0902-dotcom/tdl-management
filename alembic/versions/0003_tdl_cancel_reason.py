"""Add TDL cancel reason.

Revision ID: 0003_tdl_cancel_reason
Revises: 0002_calendar_authorizations
Create Date: 2026-05-18 04:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_tdl_cancel_reason"
down_revision: Union[str, None] = "0002_calendar_authorizations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tdls", sa.Column("cancel_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("tdls", "cancel_reason")
