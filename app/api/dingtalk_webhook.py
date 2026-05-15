from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.integrations.dingtalk_card import build_created_card
from app.schemas import DingTalkAction, DingTalkIncomingMessage
from app.services.intake_service import intake_dingtalk_message
from app.services.tdl_service import confirm_tdl


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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return build_created_card(tdl)
