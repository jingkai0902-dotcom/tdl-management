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
        title: str,
        due_at: datetime,
        description: str | None = None,
        duration_minutes: int = 30,
        is_busy: bool = True,
    ) -> str:
        token = await self._get_openapi_access_token()
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/calendar/users/{owner_union_id}/calendars/primary/events",
            headers={"x-acs-dingtalk-access-token": token},
            json=self._calendar_event_request_body(
                title=title,
                due_at=due_at,
                description=description,
                duration_minutes=duration_minutes,
                is_busy=is_busy,
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
        title: str,
        due_at: datetime,
        description: str | None = None,
        duration_minutes: int = 30,
        is_busy: bool = True,
    ) -> str:
        token = await self._get_openapi_access_token()
        response = await self.http_client.put(
            f"{OPENAPI_BASE_URL}/v1.0/calendar/users/{owner_union_id}/calendars/primary/events/{event_id}",
            headers={"x-acs-dingtalk-access-token": token},
            json=self._calendar_event_request_body(
                title=title,
                due_at=due_at,
                description=description,
                duration_minutes=duration_minutes,
                is_busy=is_busy,
            ),
        )
        payload = response.json()
        if response.status_code >= 400 or payload.get("code"):
            raise DingTalkAPIError(f"Failed to update DingTalk calendar event: {payload}")
        return event_id

    async def create_work_todo_task(
        self,
        *,
        owner_union_id: str,
        title: str,
        detail_url: str,
        operator_id: str | None = None,
        creator_id: str | None = None,
        description: str | None = None,
        due_at: datetime | None = None,
        participant_ids: list[str] | None = None,
        source_id: str | None = None,
        priority: int | None = None,
        ding_notify: str | None = None,
    ) -> str:
        """Create an enterprise work todo with app-level credentials."""
        if not detail_url.strip():
            raise DingTalkAPIError("DingTalk work todo requires detail_url")
        token = await self._get_openapi_access_token()
        resolved_operator_id = operator_id or owner_union_id
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/todo/users/{owner_union_id}/tasks",
            params={"operatorId": resolved_operator_id},
            headers={"x-acs-dingtalk-access-token": token},
            json=self._work_todo_request_body(
                owner_union_id=owner_union_id,
                title=title,
                detail_url=detail_url,
                creator_id=creator_id or resolved_operator_id,
                description=description,
                due_at=due_at,
                participant_ids=participant_ids,
                source_id=source_id,
                priority=priority,
                ding_notify=ding_notify,
            ),
        )
        payload = response.json()
        task_id = self._extract_todo_task_id(payload)
        if response.status_code >= 400 or payload.get("code") or not task_id:
            raise DingTalkAPIError(f"Failed to create DingTalk work todo task: {payload}")
        return task_id

    async def create_personal_todo_task(
        self,
        *,
        user_access_token: str,
        title: str,
        description: str | None = None,
        due_at: datetime | None = None,
        executor_ids: list[str] | None = None,
        participant_ids: list[str] | None = None,
        ding_notify: str | None = None,
    ) -> str:
        """Create a personal todo with the caller's user OAuth token."""
        response = await self.http_client.post(
            f"{OPENAPI_BASE_URL}/v1.0/todo/users/me/personalTasks",
            headers={"x-acs-dingtalk-access-token": user_access_token},
            json=self._personal_todo_request_body(
                title=title,
                description=description,
                due_at=due_at,
                executor_ids=executor_ids,
                participant_ids=participant_ids,
                ding_notify=ding_notify,
            ),
        )
        payload = response.json()
        task_id = self._extract_todo_task_id(payload)
        if response.status_code >= 400 or payload.get("code") or not task_id:
            raise DingTalkAPIError(f"Failed to create DingTalk personal todo task: {payload}")
        return task_id

    def _calendar_event_request_body(
        self,
        *,
        title: str,
        due_at: datetime,
        description: str | None = None,
        duration_minutes: int = 30,
        is_busy: bool = True,
    ) -> dict:
        due_at_local = due_at.astimezone(SHANGHAI_TZ)
        start_at_local = (due_at - timedelta(minutes=duration_minutes)).astimezone(SHANGHAI_TZ)
        body = {
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
            "showMeAs": "busy" if is_busy else "free",
            "reminders": [
                {
                    "method": "dingtalk",
                    "minutes": 5,
                }
            ],
        }
        return body

    def _work_todo_request_body(
        self,
        *,
        owner_union_id: str,
        title: str,
        detail_url: str,
        creator_id: str,
        description: str | None = None,
        due_at: datetime | None = None,
        participant_ids: list[str] | None = None,
        source_id: str | None = None,
        priority: int | None = None,
        ding_notify: str | None = None,
    ) -> dict:
        body = {
            "subject": title,
            "creatorId": creator_id,
            "description": description or "",
            "executorIds": [owner_union_id],
            "participantIds": participant_ids or [],
            "detailUrl": {
                "appUrl": detail_url,
                "pcUrl": detail_url,
            },
        }
        if due_at is not None:
            body["dueTime"] = self._to_unix_millis(due_at)
        if source_id:
            body["sourceId"] = source_id
        if priority is not None:
            body["priority"] = priority
        if ding_notify is not None:
            body["notifyConfigs"] = {"dingNotify": ding_notify}
        return body

    def _personal_todo_request_body(
        self,
        *,
        title: str,
        description: str | None = None,
        due_at: datetime | None = None,
        executor_ids: list[str] | None = None,
        participant_ids: list[str] | None = None,
        ding_notify: str | None = None,
    ) -> dict:
        body = {
            "subject": title,
            "description": description or "",
            "executorIds": executor_ids or [],
            "participantIds": participant_ids or [],
        }
        if due_at is not None:
            body["dueTime"] = self._to_unix_millis(due_at)
        if ding_notify is not None:
            body["notifyConfigs"] = {"dingNotify": ding_notify}
        return body

    def _extract_todo_task_id(self, payload: dict) -> str | None:
        task_id = payload.get("taskId") or payload.get("id")
        if task_id:
            return str(task_id)
        result = payload.get("result")
        if isinstance(result, dict):
            task_id = result.get("taskId") or result.get("id")
            if task_id:
                return str(task_id)
        return None

    def _to_unix_millis(self, value: datetime) -> int:
        if value.tzinfo is None:
            raise DingTalkAPIError("DingTalk todo due_at must include timezone information")
        return int(value.timestamp() * 1000)

    def build_user_authorization_url(self, *, redirect_uri: str, state: str) -> str:
        settings = get_settings()
        if not self.app_key:
            raise DingTalkAPIError("Missing DingTalk app_key for OAuth")
        query = urlencode(
            {
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "client_id": self.app_key,
                "scope": settings.dingtalk_oauth_scope or "openid",
                "state": state,
                "prompt": "consent",
            }
        )
        return f"{LOGIN_BASE_URL}/oauth2/auth?{query}"

    async def exchange_user_authorization_code(self, code: str) -> dict:
        if not self.app_key or not self.app_secret:
            raise DingTalkAPIError("Missing DingTalk OAuth client credentials")
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
        if not self.app_key or not self.app_secret:
            raise DingTalkAPIError("Missing DingTalk OAuth client credentials")
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

    async def get_user_id_by_union_id(self, union_id: str) -> str:
        token = await self._get_access_token()
        response = await self.http_client.post(
            "/topapi/user/getbyunionid",
            params={"access_token": token},
            json={"unionid": union_id},
        )
        payload = response.json()
        result = payload.get("result") or {}
        user_id = result.get("userid") or payload.get("userid")
        if payload.get("errcode") != 0 or not user_id:
            raise DingTalkAPIError(f"Failed to resolve DingTalk user id from union id: {payload}")
        return str(user_id)

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
