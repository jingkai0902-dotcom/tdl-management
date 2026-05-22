from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntakeDiffLog, TDL


TRACKED_FIELDS = ("title", "owner_id", "due_at", "completion_criteria", "priority")


def tdl_payload(tdl: TDL) -> dict[str, Any]:
    return {
        field_name: _jsonable(getattr(tdl, field_name))
        for field_name in TRACKED_FIELDS
    }


def diff_field_names(
    draft_payload: dict[str, Any] | None,
    confirmed_payload: dict[str, Any] | None,
) -> list[str]:
    draft = draft_payload or {}
    confirmed = confirmed_payload or {}
    fields = sorted(set(draft) | set(confirmed))
    return [
        field_name
        for field_name in fields
        if draft.get(field_name) != confirmed.get(field_name)
    ]


def add_intake_diff_log(
    session: AsyncSession,
    *,
    tdl: TDL | None,
    action_type: str,
    source: str,
    actor_id: str | None,
    raw_text: str | None = None,
    message_id: str | None = None,
    draft_payload: dict[str, Any] | None = None,
    confirmed_payload: dict[str, Any] | None = None,
) -> IntakeDiffLog:
    log = IntakeDiffLog(
        tdl_id=tdl.tdl_id if tdl is not None else None,
        message_id=message_id,
        raw_text=raw_text,
        action_type=action_type,
        source=source,
        actor_id=actor_id,
        draft_payload=draft_payload,
        confirmed_payload=confirmed_payload,
        diff_fields=diff_field_names(draft_payload, confirmed_payload),
    )
    session.add(log)
    return log


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value
