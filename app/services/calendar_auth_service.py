from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, load_yaml_config
from app.integrations.dingtalk_client import DingTalkClient
from app.models import CalendarAuthorization


STATE_TTL_MINUTES = 15


def _management_user_ids() -> set[str]:
    roster = load_yaml_config("management_roster.yaml")
    return {
        str(member["dingtalk_user_id"])
        for member in roster.get("management", [])
        if member.get("dingtalk_user_id")
    }


def _state_secret() -> bytes:
    settings = get_settings()
    if not settings.dingtalk_app_secret:
        raise ValueError("Missing DINGTALK_APP_SECRET")
    return settings.dingtalk_app_secret.encode()


def _encode_part(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_part(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def build_calendar_auth_state(user_id: str, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "user_id": user_id,
        "exp": int((issued_at + timedelta(minutes=STATE_TTL_MINUTES)).timestamp()),
    }
    payload_part = _encode_part(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(_state_secret(), payload_part.encode(), hashlib.sha256).digest()
    return f"{payload_part}.{_encode_part(signature)}"


def parse_calendar_auth_state(state: str, *, now: datetime | None = None) -> str:
    try:
        payload_part, signature_part = state.split(".", maxsplit=1)
        expected_signature = hmac.new(_state_secret(), payload_part.encode(), hashlib.sha256).digest()
        actual_signature = _decode_part(signature_part)
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("Invalid calendar auth state signature")
        payload = json.loads(_decode_part(payload_part))
        if int(payload["exp"]) < int((now or datetime.now(UTC)).timestamp()):
            raise ValueError("Calendar auth state expired")
        user_id = str(payload["user_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid calendar auth state") from exc
    if user_id not in _management_user_ids():
        raise ValueError("Calendar auth user is outside the management roster")
    return user_id


def get_calendar_auth_callback_url() -> str:
    settings = get_settings()
    if settings.dingtalk_oauth_redirect_uri:
        return settings.dingtalk_oauth_redirect_uri
    if not settings.public_base_url:
        raise ValueError("Missing DINGTALK_OAUTH_REDIRECT_URI or PUBLIC_BASE_URL")
    return f"{settings.public_base_url.rstrip('/')}/calendar/auth/callback"


def build_calendar_auth_start_url(user_id: str) -> str:
    settings = get_settings()
    if not settings.public_base_url:
        raise ValueError("Missing PUBLIC_BASE_URL")
    return f"{settings.public_base_url.rstrip('/')}/calendar/auth/start?user_id={quote(user_id)}"


async def store_calendar_authorization(
    session: AsyncSession,
    *,
    dingtalk_user_id: str,
    token_payload: dict,
    union_id: str,
    now: datetime | None = None,
) -> CalendarAuthorization:
    current_time = now or datetime.now(UTC)
    authorization = await session.get(CalendarAuthorization, dingtalk_user_id)
    if authorization is None:
        authorization = CalendarAuthorization(
            dingtalk_user_id=dingtalk_user_id,
            union_id=union_id,
            access_token=token_payload["accessToken"],
            refresh_token=token_payload["refreshToken"],
            access_token_expires_at=current_time + timedelta(seconds=int(token_payload["expireIn"])),
            refresh_token_expires_at=_refresh_token_expires_at(token_payload, current_time),
            scope=token_payload.get("scope"),
        )
        session.add(authorization)
    else:
        authorization.union_id = union_id
        authorization.access_token = token_payload["accessToken"]
        authorization.refresh_token = token_payload["refreshToken"]
        authorization.access_token_expires_at = current_time + timedelta(
            seconds=int(token_payload["expireIn"])
        )
        authorization.refresh_token_expires_at = _refresh_token_expires_at(
            token_payload,
            current_time,
        )
        authorization.scope = token_payload.get("scope")
    await session.commit()
    await session.refresh(authorization)
    return authorization


def _refresh_token_expires_at(token_payload: dict, current_time: datetime) -> datetime | None:
    refresh_expire_in = token_payload.get("refreshTokenExpireIn")
    if refresh_expire_in is None:
        return None
    return current_time + timedelta(seconds=int(refresh_expire_in))


async def get_valid_calendar_authorization(
    session: AsyncSession,
    *,
    dingtalk_user_id: str,
    client: DingTalkClient | None = None,
    now: datetime | None = None,
) -> CalendarAuthorization | None:
    current_time = now or datetime.now(UTC)
    authorization = await session.get(CalendarAuthorization, dingtalk_user_id)
    if authorization is None:
        return None
    if authorization.access_token_expires_at > current_time:
        return authorization
    if (
        authorization.refresh_token_expires_at is not None
        and authorization.refresh_token_expires_at <= current_time
    ):
        return None
    dingtalk_client = client or DingTalkClient()
    token_payload = await dingtalk_client.refresh_user_access_token(authorization.refresh_token)
    return await store_calendar_authorization(
        session,
        dingtalk_user_id=dingtalk_user_id,
        token_payload=token_payload,
        union_id=authorization.union_id,
        now=current_time,
    )
