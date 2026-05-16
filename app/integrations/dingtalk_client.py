from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings


OAPI_BASE_URL = "https://oapi.dingtalk.com"
OPENAPI_BASE_URL = "https://api.dingtalk.com"
LOGIN_BASE_URL = "https://login.dingtalk.com"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class DingTalkAPIError(RuntimeError):
    pass


class DingTalkClient:
    def __init__(
        self,
        *,
        app_key: str | None = None,
        app_secret: str | None = None,
        agent_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.app_key = app_key if app_key is not None else settings.dingtalk_app_key
        self.app_secret = app_secret if app_secret is not None else settings.dingtalk_app_secret
        self.agent_id = agent_id if agent_id is not None else settings.dingtalk_agent_id
        self.http_client = http_client or httpx.AsyncClient(
            base_url=OAPI_BASE_URL,
            timeout=10.0,
        )
        self._owns_http_client = http_client is None
        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None
        self._openapi_access_token: str | None = None
        self._openapi_access_token_expires_at: datetime | None = None

    async def close(self) -> None:
        if self._owns_http_client:
            await self.http_client.aclose()

    async def send_work_markdown(
        self,
        *,
        user_ids: list[str],
        title: str,
        text: str,
    ) -> None:
        if not self.agent_id:
            raise DingTalkAPIError("Missing DingTalk agent_id")
        token = await self._get_access_token()
        response = await self.http_client.post(
            "/topapi/message/corpconversation/asyncsend_v2",
            params={"access_token": token},
            json={
                "agent_id": self.agent_id,
                "userid_list": ",".join(user_ids),
                "msg": {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": title,
                        "text": text,
                    },
                },
            },
        )
        payload = response.json()
        if payload.get("errcode") != 0:
            raise DingTalkAPIError(f"Failed to send DingTalk work message: {payload}")

    async def send_interactive_card_to_user(
        self,
        *,
        user_id: str,
        card_template_id: str,
        card_data: dict[str, str],
        out_track_id: str | None = None,
    ) -> str:
        token = await self._get_openapi_access_token()
        resolved_out_track_id = out_track_id or str(uuid4())
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/card/instances/createAndDeliver",
            headers={"x-acs-dingtalk-access-token": token},
            json={
                "cardTemplateId": card_template_id,
                "outTrackId": resolved_out_track_id,
                "cardData": {"cardParamMap": card_data},
                "callbackType": "STREAM",
                "openSpaceId": f"dtv1.card//IM_ROBOT.{user_id}",
                "imRobotOpenSpaceModel": {"supportForward": False},
                "imRobotOpenDeliverModel": {"spaceType": "IM_ROBOT"},
            },
        )
        payload = response.json()
        if response.status_code >= 400 or payload.get("code"):
            raise DingTalkAPIError(f"Failed to send DingTalk interactive card: {payload}")
        return resolved_out_track_id

    async def create_tdl_calendar_event(
        self,
        *,
        owner_union_id: str,
        user_access_token: str,
        title: str,
        due_at: datetime,
        description: str | None = None,
        duration_minutes: int = 30,
    ) -> str:
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/calendar/users/{owner_union_id}/calendars/primary/events",
            headers={"x-acs-dingtalk-access-token": user_access_token},
            json=self._calendar_event_request_body(
                title=title,
                due_at=due_at,
                description=description,
                duration_minutes=duration_minutes,
            ),
        )
        payload = response.json()
        event_id = payload.get("id")
        if response.status_code >= 400 or payload.get("code") or not event_id:
            raise DingTalkAPIError(f"Failed to create DingTalk calendar event: {payload}")
        return event_id

    async def update_tdl_calendar_event(
        self,
        *,
        event_id: str,
        owner_union_id: str,
        user_access_token: str,
        title: str,
        due_at: datetime,
        description: str | None = None,
        duration_minutes: int = 30,
    ) -> str:
        response = await self.http_client.put(
            f"{OPENAPI_BASE_URL}/v1.0/calendar/users/{owner_union_id}/calendars/primary/events/{event_id}",
            headers={"x-acs-dingtalk-access-token": user_access_token},
            json=self._calendar_event_request_body(
                title=title,
                due_at=due_at,
                description=description,
                duration_minutes=duration_minutes,
            ),
        )
        payload = response.json()
        if response.status_code >= 400 or payload.get("code"):
            raise DingTalkAPIError(f"Failed to update DingTalk calendar event: {payload}")
        return event_id

    def _calendar_event_request_body(
        self,
        *,
        title: str,
        due_at: datetime,
        description: str | None = None,
        duration_minutes: int = 30,
    ) -> dict:
        due_at_local = due_at.astimezone(SHANGHAI_TZ)
        start_at_local = (due_at - timedelta(minutes=duration_minutes)).astimezone(SHANGHAI_TZ)
        return {
            "summary": title,
            "description": description or "",
            "start": {
                "dateTime": start_at_local.isoformat(),
                "timeZone": "Asia/Shanghai",
            },
            "end": {
                "dateTime": due_at_local.isoformat(),
                "timeZone": "Asia/Shanghai",
            },
        }

    def build_user_authorization_url(self, *, redirect_uri: str, state: str) -> str:
        if not self.app_key:
            raise DingTalkAPIError("Missing DingTalk app_key")
        query = urlencode(
            {
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "client_id": self.app_key,
                "scope": "openid",
                "state": state,
                "prompt": "consent",
            }
        )
        return f"{LOGIN_BASE_URL}/oauth2/auth?{query}"

    async def exchange_user_authorization_code(self, code: str) -> dict:
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/oauth2/userAccessToken",
            json={
                "clientId": self.app_key,
                "clientSecret": self.app_secret,
                "code": code,
                "grantType": "authorization_code",
            },
        )
        payload = response.json()
        if response.status_code >= 400 or not payload.get("accessToken"):
            raise DingTalkAPIError(f"Failed to exchange DingTalk user authorization code: {payload}")
        return payload

    async def refresh_user_access_token(self, refresh_token: str) -> dict:
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/oauth2/userAccessToken",
            json={
                "clientId": self.app_key,
                "clientSecret": self.app_secret,
                "refreshToken": refresh_token,
                "grantType": "refresh_token",
            },
        )
        payload = response.json()
        if response.status_code >= 400 or not payload.get("accessToken"):
            raise DingTalkAPIError(f"Failed to refresh DingTalk user access token: {payload}")
        return payload

    async def get_current_user_profile(self, user_access_token: str) -> dict:
        response = await self.http_client.get(
            f"{OPENAPI_BASE_URL}/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": user_access_token},
        )
        payload = response.json()
        if response.status_code >= 400 or payload.get("code") or not payload.get("unionId"):
            raise DingTalkAPIError(f"Failed to get DingTalk current user profile: {payload}")
        return payload

    async def _get_access_token(self) -> str:
        if (
            self._access_token is not None
            and self._access_token_expires_at is not None
            and datetime.now(UTC) < self._access_token_expires_at
        ):
            return self._access_token
        if not self.app_key or not self.app_secret:
            raise DingTalkAPIError("Missing DingTalk app credentials")
        response = await self.http_client.get(
            "/gettoken",
            params={"appkey": self.app_key, "appsecret": self.app_secret},
        )
        payload = response.json()
        if payload.get("errcode") != 0 or not payload.get("access_token"):
            raise DingTalkAPIError(f"Failed to get DingTalk access token: {payload}")
        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 7200))
        self._access_token_expires_at = datetime.now(UTC) + timedelta(
            seconds=max(expires_in - 300, 0)
        )
        return self._access_token

    async def _get_openapi_access_token(self) -> str:
        if (
            self._openapi_access_token is not None
            and self._openapi_access_token_expires_at is not None
            and datetime.now(UTC) < self._openapi_access_token_expires_at
        ):
            return self._openapi_access_token
        if not self.app_key or not self.app_secret:
            raise DingTalkAPIError("Missing DingTalk app credentials")
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/oauth2/accessToken",
            json={"appKey": self.app_key, "appSecret": self.app_secret},
        )
        payload = response.json()
        if response.status_code >= 400 or not payload.get("accessToken"):
            raise DingTalkAPIError(f"Failed to get DingTalk OpenAPI access token: {payload}")
        self._openapi_access_token = payload["accessToken"]
        expires_in = int(payload.get("expireIn", 7200))
        self._openapi_access_token_expires_at = datetime.now(UTC) + timedelta(
            seconds=max(expires_in - 300, 0)
        )
        return self._openapi_access_token
