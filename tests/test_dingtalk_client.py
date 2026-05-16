import httpx
import pytest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from app.config import get_settings
from app.integrations.dingtalk_client import DingTalkAPIError, DingTalkClient


@pytest.mark.asyncio
async def test_send_work_markdown_fetches_token_and_sends_message() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/gettoken":
            return httpx.Response(200, json={"errcode": 0, "access_token": "token-1", "expires_in": 7200})
        return httpx.Response(200, json={"errcode": 0})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://oapi.dingtalk.com",
    ) as http_client:
        client = DingTalkClient(
            app_key="app-key",
            app_secret="app-secret",
            agent_id="agent-1",
            http_client=http_client,
        )

        await client.send_work_markdown(
            user_ids=["user-1"],
            title="今日待办",
            text="## 今日待办",
        )
        await client.send_work_markdown(
            user_ids=["user-2"],
            title="任务提醒",
            text="## 任务提醒",
        )

    assert [request.url.path for request in requests] == [
        "/gettoken",
        "/topapi/message/corpconversation/asyncsend_v2",
        "/topapi/message/corpconversation/asyncsend_v2",
    ]
    assert requests[1].url.params["access_token"] == "token-1"
    assert requests[1].read().decode() == (
        '{"agent_id":"agent-1","userid_list":"user-1","msg":{"msgtype":"markdown",'
        '"markdown":{"title":"今日待办","text":"## 今日待办"}}}'
    )


@pytest.mark.asyncio
async def test_send_work_markdown_raises_on_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gettoken":
            return httpx.Response(200, json={"errcode": 0, "access_token": "token-1"})
        return httpx.Response(200, json={"errcode": 123, "errmsg": "failed"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://oapi.dingtalk.com",
    ) as http_client:
        client = DingTalkClient(
            app_key="app-key",
            app_secret="app-secret",
            agent_id="agent-1",
            http_client=http_client,
        )

        with pytest.raises(DingTalkAPIError, match="Failed to send DingTalk work message"):
            await client.send_work_markdown(
                user_ids=["user-1"],
                title="今日待办",
                text="## 今日待办",
            )


@pytest.mark.asyncio
async def test_send_interactive_card_uses_openapi_token_and_delivery_endpoint() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1.0/oauth2/accessToken":
            return httpx.Response(200, json={"accessToken": "openapi-token", "expireIn": 7200})
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DingTalkClient(
            app_key="app-key",
            app_secret="app-secret",
            agent_id="agent-1",
            http_client=http_client,
        )

        out_track_id = await client.send_interactive_card_to_user(
            user_id="user-1",
            card_template_id="template.schema",
            card_data={"msgTitle": "今日待办"},
            out_track_id="track-1",
        )

    assert out_track_id == "track-1"
    assert [request.url.path for request in requests] == [
        "/v1.0/oauth2/accessToken",
        "/v1.0/card/instances/createAndDeliver",
    ]
    assert requests[1].headers["x-acs-dingtalk-access-token"] == "openapi-token"
    assert requests[1].read().decode() == (
        '{"cardTemplateId":"template.schema","outTrackId":"track-1",'
        '"cardData":{"cardParamMap":{"msgTitle":"今日待办"}},'
        '"callbackType":"STREAM","openSpaceId":"dtv1.card//IM_ROBOT.user-1",'
        '"imRobotOpenSpaceModel":{"supportForward":false},'
        '"imRobotOpenDeliverModel":{"spaceType":"IM_ROBOT"}}'
    )


@pytest.mark.asyncio
async def test_create_tdl_calendar_event_uses_primary_calendar() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "evt-1"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://oapi.dingtalk.com",
    ) as http_client:
        client = DingTalkClient(
            app_key="app-key",
            app_secret="app-secret",
            agent_id="agent-1",
            http_client=http_client,
        )

        event_id = await client.create_tdl_calendar_event(
            owner_user_id="user-1",
            user_access_token="user-token",
            title="完成招生方案",
            due_at=datetime(2026, 5, 20, 18, 0, tzinfo=UTC),
            description="TDL ID: tdl-1",
        )

    assert event_id == "evt-1"
    assert [request.url.path for request in requests] == [
        "/v1.0/calendar/users/user-1/calendars/primary/events",
    ]
    assert requests[0].headers["x-acs-dingtalk-access-token"] == "user-token"
    assert requests[0].read().decode() == (
        '{"summary":"完成招生方案","description":"TDL ID: tdl-1",'
        '"start":{"dateTime":"2026-05-21T01:30:00+08:00","timeZone":"Asia/Shanghai"},'
        '"end":{"dateTime":"2026-05-21T02:00:00+08:00","timeZone":"Asia/Shanghai"}}'
    )


@pytest.mark.asyncio
async def test_update_tdl_calendar_event_uses_existing_event_id() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://oapi.dingtalk.com",
    ) as http_client:
        client = DingTalkClient(
            app_key="app-key",
            app_secret="app-secret",
            agent_id="agent-1",
            http_client=http_client,
        )

        event_id = await client.update_tdl_calendar_event(
            event_id="evt-1",
            owner_user_id="user-1",
            user_access_token="user-token",
            title="完成招生方案",
            due_at=datetime(2026, 5, 22, 18, 0, tzinfo=UTC),
            description="TDL ID: tdl-1",
        )

    assert event_id == "evt-1"
    assert [request.url.path for request in requests] == [
        "/v1.0/calendar/users/user-1/calendars/primary/events/evt-1",
    ]
    assert requests[0].headers["x-acs-dingtalk-access-token"] == "user-token"
    assert requests[0].read().decode() == (
        '{"summary":"完成招生方案","description":"TDL ID: tdl-1",'
        '"start":{"dateTime":"2026-05-23T01:30:00+08:00","timeZone":"Asia/Shanghai"},'
        '"end":{"dateTime":"2026-05-23T02:00:00+08:00","timeZone":"Asia/Shanghai"}}'
    )


@pytest.mark.asyncio
async def test_exchange_user_authorization_code_fetches_user_token() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "accessToken": "user-token",
                "refreshToken": "refresh-token",
                "expireIn": 7200,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DingTalkClient(
            app_key="app-key",
            app_secret="app-secret",
            agent_id="agent-1",
            http_client=http_client,
        )

        payload = await client.exchange_user_authorization_code("auth-code")

    assert payload["accessToken"] == "user-token"
    assert [request.url.path for request in requests] == ["/v1.0/oauth2/userAccessToken"]
    assert requests[0].read().decode() == (
        '{"clientId":"app-key","clientSecret":"app-secret","code":"auth-code",'
        '"grantType":"authorization_code"}'
    )


def test_build_user_authorization_url_uses_oauth_client_id(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DINGTALK_OAUTH_CLIENT_ID", "oauth-client-id")
    monkeypatch.setenv("DINGTALK_OAUTH_SCOPE", "openid Contact.User.Read Calendar.Event.Write")
    try:
        client = DingTalkClient(app_key="app-key", app_secret="app-secret", agent_id="agent-1")

        url = client.build_user_authorization_url(
            redirect_uri="https://example.com/calendar/auth/callback",
            state="state-1",
        )
    finally:
        get_settings.cache_clear()

    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["oauth-client-id"]
    assert query["scope"] == ["openid Contact.User.Read Calendar.Event.Write"]
    assert query["redirect_uri"] == ["https://example.com/calendar/auth/callback"]


@pytest.mark.asyncio
async def test_exchange_user_authorization_code_uses_oauth_client_secret(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DINGTALK_OAUTH_CLIENT_ID", "oauth-client-id")
    monkeypatch.setenv("DINGTALK_OAUTH_CLIENT_SECRET", "oauth-client-secret")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "accessToken": "user-token",
                "refreshToken": "refresh-token",
                "expireIn": 7200,
            },
        )

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = DingTalkClient(
                app_key="app-key",
                app_secret="app-secret",
                agent_id="agent-1",
                http_client=http_client,
            )

            payload = await client.exchange_user_authorization_code("auth-code")
    finally:
        get_settings.cache_clear()

    assert payload["accessToken"] == "user-token"
    assert requests[0].read().decode() == (
        '{"clientId":"oauth-client-id","clientSecret":"oauth-client-secret",'
        '"code":"auth-code","grantType":"authorization_code"}'
    )


@pytest.mark.asyncio
async def test_get_user_id_by_union_id_uses_oapi_mapping() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/gettoken":
            return httpx.Response(
                200,
                json={"errcode": 0, "access_token": "app-token", "expires_in": 7200},
            )
        return httpx.Response(
            200,
            json={"errcode": 0, "result": {"userid": "user-1"}},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://oapi.dingtalk.com",
    ) as http_client:
        client = DingTalkClient(
            app_key="app-key",
            app_secret="app-secret",
            agent_id="agent-1",
            http_client=http_client,
        )

        user_id = await client.get_user_id_by_union_id("union-1")

    assert user_id == "user-1"
    assert [request.url.path for request in requests] == [
        "/gettoken",
        "/topapi/user/getbyunionid",
    ]
    assert requests[1].url.params["access_token"] == "app-token"
    assert requests[1].read().decode() == '{"unionid":"union-1"}'
