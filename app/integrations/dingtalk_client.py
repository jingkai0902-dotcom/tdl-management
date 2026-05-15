from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.config import get_settings


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
            base_url="https://oapi.dingtalk.com",
            timeout=10.0,
        )
        self._owns_http_client = http_client is None
        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None

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
