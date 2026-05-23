from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, TDL
from app.schemas import BatchConfirmDraftsRead, TDLCreate, TDLDraftCreate, TDLDraftUpdate, TDLRead
from app.services.intake_diff_service import add_intake_diff_log, tdl_payload


ACTIONABLE_STATUSES = {"active", "attention", "snoozed"}
FOLLOW_UP_SOURCES = {"dingtalk_msg", "button_validation"}


async def create_tdl(session: AsyncSession, payload: TDLCreate) -> TDL:
    tdl = TDL(**payload.model_dump(), status="active")
    session.add(tdl)
    await session.flush()

    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="create",
            actor_id=payload.created_by,
            payload=payload.model_dump(mode="json"),
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def create_draft_tdl(session: AsyncSession, payload: TDLDraftCreate) -> TDL:
    data = payload.model_dump(exclude={"raw_text"})
    data["status"] = "draft"
    tdl = TDL(**data)
    session.add(tdl)
    await session.flush()

    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="draft_create",
            actor_id=payload.created_by,
            payload=payload.model_dump(mode="json"),
        )
    )
    if payload.source == "dingtalk_msg":
        add_intake_diff_log(
            session,
            tdl=tdl,
            action_type="draft_created",
            source=payload.source,
            actor_id=payload.created_by,
            raw_text=payload.raw_text,
            draft_payload=None,
            confirmed_payload=tdl_payload(tdl),
        )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def cancel_draft_tdl(session: AsyncSession, tdl_id, actor_id: str) -> TDL:
    tdl = await session.get(TDL, tdl_id)
    if tdl is None:
        raise ValueError("TDL not found")
    if tdl.status != "draft":
        raise ValueError("Only draft TDLs can be canceled through draft intake")
    tdl.status = "canceled"
    tdl.cancel_reason = "draft_ignored"
    previous = tdl_payload(tdl)
    add_intake_diff_log(
        session,
        tdl=tdl,
        action_type="canceled",
        source=tdl.source,
        actor_id=actor_id,
        draft_payload=previous,
        confirmed_payload={**previous, "status": tdl.status, "cancel_reason": tdl.cancel_reason},
    )
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="cancel",
            actor_id=actor_id,
            payload={"reason": tdl.cancel_reason},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def confirm_tdl(session: AsyncSession, tdl_id, actor_id: str) -> TDL:
    tdl = await session.get(TDL, tdl_id)
    if tdl is None:
        raise ValueError("TDL not found")
    missing_fields = [
        field_name
        for field_name in ("owner_id", "due_at")
        if getattr(tdl, field_name) is None
    ]
    if missing_fields:
        raise ValueError(f"TDL draft missing required fields: {', '.join(missing_fields)}")
    previous = tdl_payload(tdl)
    tdl.status = "active"
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="confirm",
            actor_id=actor_id,
            payload={},
        )
    )
    add_intake_diff_log(
        session,
        tdl=tdl,
        action_type="confirmed",
        source=tdl.source,
        actor_id=actor_id,
        draft_payload=previous,
        confirmed_payload={**tdl_payload(tdl), "status": tdl.status},
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def update_draft_tdl(
    session: AsyncSession,
    tdl_id,
    payload: TDLDraftUpdate,
    actor_id: str,
) -> TDL:
    tdl = await session.get(TDL, tdl_id)
    if tdl is None:
        raise ValueError("TDL not found")
    if tdl.status != "draft":
        raise ValueError("Only draft TDLs can be updated through draft completion")

    updates = payload.model_dump(exclude_none=True)
    previous = tdl_payload(tdl)
    for field_name, value in updates.items():
        setattr(tdl, field_name, value)

    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="draft_update",
            actor_id=actor_id,
            payload=payload.model_dump(mode="json", exclude_none=True),
        )
    )
    if updates:
        add_intake_diff_log(
            session,
            tdl=tdl,
            action_type="draft_updated",
            source=tdl.source,
            actor_id=actor_id,
            draft_payload=previous,
            confirmed_payload=tdl_payload(tdl),
        )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def update_open_tdl_from_follow_up(
    session: AsyncSession,
    tdl_id,
    payload: TDLDraftUpdate,
    actor_id: str,
) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)

    updates = payload.model_dump(exclude_none=True)
    previous = {field_name: getattr(tdl, field_name) for field_name in updates}
    for field_name, value in updates.items():
        setattr(tdl, field_name, value)

    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="follow_up_update",
            actor_id=actor_id,
            payload={
                "previous": {
                    field_name: (
                        value.isoformat()
                        if isinstance(value, datetime)
                        else value
                    )
                    for field_name, value in previous.items()
                },
                "updates": payload.model_dump(mode="json", exclude_none=True),
            },
        )
    )
    if updates:
        add_intake_diff_log(
            session,
            tdl=tdl,
            action_type="follow_up_updated",
            source=tdl.source,
            actor_id=actor_id,
            draft_payload={
                field_name: (
                    value.isoformat()
                    if isinstance(value, datetime)
                    else value
                )
                for field_name, value in previous.items()
            },
            confirmed_payload=tdl_payload(tdl),
        )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def confirm_ready_drafts(
    session: AsyncSession,
    tdl_ids: list,
    actor_id: str,
) -> BatchConfirmDraftsRead:
    confirmed_entities = []
    skipped = []

    for tdl_id in tdl_ids:
        tdl = await session.get(TDL, tdl_id)
        if tdl is None:
            continue
        tdl_read = TDLRead.from_tdl(tdl)
        if tdl.status != "draft" or tdl_read.missing_fields:
            skipped.append(tdl_read)
            continue
        tdl.status = "active"
        session.add(
            AuditLog(
                entity_type="tdl",
                entity_id=str(tdl.tdl_id),
                action="confirm",
                actor_id=actor_id,
                payload={"batch": True},
            )
        )
        confirmed_entities.append(tdl)

    await session.commit()
    for tdl in confirmed_entities:
        await session.refresh(tdl)

    return BatchConfirmDraftsRead(
        confirmed=[TDLRead.from_tdl(tdl) for tdl in confirmed_entities],
        skipped=skipped,
    )


async def complete_tdl(session: AsyncSession, tdl_id, actor_id: str) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    _ensure_current_owner(tdl, actor_id)
    tdl.status = "done"
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="complete",
            actor_id=actor_id,
            payload={},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def postpone_tdl(
    session: AsyncSession,
    tdl_id,
    *,
    due_at: datetime,
    actor_id: str,
) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    _ensure_current_owner(tdl, actor_id)
    previous_due_at = tdl.due_at
    tdl.due_at = due_at
    if tdl.status == "snoozed":
        tdl.status = "active"
        tdl.snooze_until = None
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="postpone",
            actor_id=actor_id,
            payload={
                "previous_due_at": previous_due_at.isoformat() if previous_due_at else None,
                "due_at": due_at.isoformat(),
            },
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def snooze_tdl(
    session: AsyncSession,
    tdl_id,
    *,
    snooze_until: datetime,
    actor_id: str,
) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    _ensure_current_owner(tdl, actor_id)
    tdl.status = "snoozed"
    tdl.snooze_until = snooze_until
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="snooze",
            actor_id=actor_id,
            payload={"snooze_until": snooze_until.isoformat()},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def request_help_tdl(session: AsyncSession, tdl_id, actor_id: str) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    _ensure_current_owner(tdl, actor_id)
    tdl.status = "attention"
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="need_help",
            actor_id=actor_id,
            payload={},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def reject_tdl(
    session: AsyncSession,
    tdl_id,
    actor_id: str,
    *,
    reason: str = "owner_rejected",
) -> TDL:
    tdl = await _get_actionable_tdl(session, tdl_id)
    _ensure_current_owner(tdl, actor_id)
    tdl.status = "rejected"
    tdl.cancel_reason = reason
    session.add(
        AuditLog(
            entity_type="tdl",
            entity_id=str(tdl.tdl_id),
            action="reject",
            actor_id=actor_id,
            payload={"reason": reason},
        )
    )
    await session.commit()
    await session.refresh(tdl)
    return tdl


async def _get_actionable_tdl(session: AsyncSession, tdl_id) -> TDL:
    tdl = await session.get(TDL, tdl_id)
    if tdl is None:
        raise ValueError("TDL not found")
    if tdl.status not in ACTIONABLE_STATUSES:
        raise ValueError("Only open TDLs can receive lifecycle actions")
    return tdl


def _ensure_current_owner(tdl: TDL, actor_id: str) -> None:
    if tdl.owner_id != actor_id:
        raise ValueError("Only the current owner can receive lifecycle actions")


async def list_tdls(session: AsyncSession) -> list[TDL]:
    result = await session.execute(select(TDL).order_by(TDL.created_at.desc()))
    return list(result.scalars().all())


async def find_latest_incomplete_draft(
    session: AsyncSession,
    *,
    created_by: str,
    max_age_minutes: int = 15,
) -> TDL | None:
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=max_age_minutes)
    result = await session.execute(
        select(TDL)
        .where(
            TDL.created_by == created_by,
            TDL.source.in_(FOLLOW_UP_SOURCES),
            TDL.status == "draft",
            TDL.created_at >= cutoff,
        )
        .order_by(TDL.created_at.desc())
        .limit(1)
    )
    tdl = result.scalar_one_or_none()
    if is_follow_up_candidate(
        tdl,
        now=datetime.now(tz=UTC),
        max_age_minutes=max_age_minutes,
    ):
        return tdl
    return None


async def find_latest_recent_draft(
    session: AsyncSession,
    *,
    created_by: str,
    max_age_minutes: int = 15,
) -> TDL | None:
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=max_age_minutes)
    result = await session.execute(
        select(TDL)
        .where(
            TDL.created_by == created_by,
            TDL.source.in_(FOLLOW_UP_SOURCES),
            TDL.status == "draft",
            TDL.created_at >= cutoff,
        )
        .order_by(TDL.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def find_latest_recent_open_tdl(
    session: AsyncSession,
    *,
    created_by: str,
    max_age_minutes: int = 15,
) -> TDL | None:
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=max_age_minutes)
    result = await session.execute(
        select(TDL)
        .where(
            TDL.created_by == created_by,
            TDL.source.in_(FOLLOW_UP_SOURCES),
            TDL.status.in_(ACTIONABLE_STATUSES),
            TDL.created_at >= cutoff,
        )
        .order_by(TDL.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def is_follow_up_candidate(
    tdl: TDL | None,
    *,
    now: datetime,
    max_age_minutes: int,
) -> bool:
    if tdl is None or tdl.created_at is None:
        return False
    if (
        tdl.owner_id is not None
        and tdl.due_at is not None
        and tdl.completion_criteria is not None
    ):
        return False
    return tdl.created_at >= now - timedelta(minutes=max_age_minutes)
