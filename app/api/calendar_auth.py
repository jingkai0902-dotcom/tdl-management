from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.integrations.dingtalk_client import DingTalkAPIError, DingTalkClient
from app.services.calendar_auth_service import (
    build_calendar_auth_state,
    get_calendar_auth_callback_url,
    parse_calendar_auth_state,
    store_calendar_authorization,
)


router = APIRouter(prefix="/calendar/auth", tags=["calendar-auth"])


@router.get("/start")
async def start_calendar_authorization(user_id: str) -> RedirectResponse:
    try:
        state = build_calendar_auth_state(user_id)
        redirect_uri = get_calendar_auth_callback_url()
        authorization_url = DingTalkClient().build_user_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(authorization_url)


@router.get("/callback", response_class=HTMLResponse)
async def finish_calendar_authorization(
    state: str,
    auth_code: str | None = Query(default=None, alias="authCode"),
    code: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    resolved_code = auth_code or code
    if not resolved_code:
        raise HTTPException(status_code=400, detail="Missing DingTalk authorization code")
    try:
        dingtalk_user_id = parse_calendar_auth_state(state)
        client = DingTalkClient()
        try:
            token_payload = await client.exchange_user_authorization_code(resolved_code)
            profile = await client.get_current_user_profile(token_payload["accessToken"])
            authorized_user_id = profile.get("userId") or await client.get_user_id_by_union_id(
                profile["unionId"]
            )
        finally:
            await client.close()
        if str(authorized_user_id) != dingtalk_user_id:
            raise ValueError("Calendar authorization account does not match requested user")
        await store_calendar_authorization(
            session,
            dingtalk_user_id=dingtalk_user_id,
            token_payload=token_payload,
            union_id=profile["unionId"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DingTalkAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return HTMLResponse("日历同步已开通，可以关闭这个页面。")
