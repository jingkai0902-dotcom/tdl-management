from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.integrations.dingtalk_card import build_created_card, build_draft_card
from app.schemas import (
    BatchConfirmDraftsRead,
    BatchConfirmDraftsRequest,
    DingTalkAction,
    DingTalkIncomingMessage,
    TDLDraftUpdate,
)
from app.services.intake_service import intake_dingtalk_message
from app.services.tdl_service import confirm_ready_drafts, confirm_tdl, update_draft_tdl


router = APIRouter(prefix="/dingtalk", tags=["dingtalk"])


@router.post("/messages")
async def receive_message(
    payload: DingTalkIncomingMessage,
    session: AsyncSession = Depends(get_session),
):
    card = await intake_dingtalk_message(session, payload)
    return card


@router.post("/actions/confirm")
async def confirm_action(
    payload: DingTalkAction,
    session: AsyncSession = Depends(get_session),
):
    if payload.action != "confirm":
        raise HTTPException(status_code=400, detail="Unsupported action")
    try:
        tdl = await confirm_tdl(session, payload.tdl_id, payload.actor_id)
    except ValueError as exc:
        if "missing required fields" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return build_created_card(tdl)


@router.patch("/drafts/{tdl_id}")
async def update_draft_action(
    tdl_id,
    payload: TDLDraftUpdate,
    actor_id: str,
    session: AsyncSession = Depends(get_session),
):
    try:
        tdl = await update_draft_tdl(session, tdl_id, payload, actor_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if "Only draft TDLs" in detail else 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return build_draft_card(tdl)


@router.post("/drafts/batch-confirm")
async def batch_confirm_drafts_action(
    payload: BatchConfirmDraftsRequest,
    session: AsyncSession = Depends(get_session),
) -> BatchConfirmDraftsRead:
    return await confirm_ready_drafts(session, payload.tdl_ids, payload.actor_id)
