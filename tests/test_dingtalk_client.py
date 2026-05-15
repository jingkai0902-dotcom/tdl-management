import httpx
import pytest
from datetime import UTC, datetime

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
        if request.url.path == "/gettoken":
            return httpx.Response(200, json={"errcode": 0, "access_token": "token-1"})
        return httpx.Response(200, json={"errcode": 0, "result": {"event_id": "evt-1"}})

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
            owner_id="owner-1",
            title="完成招生方案",
            due_at=datetime(2026, 5, 20, 18, 0, tzinfo=UTC),
            participant_user_ids=["owner-1", "user-2"],
            description="TDL ID: tdl-1",
        )

    assert event_id == "evt-1"
    assert [request.url.path for request in requests] == [
        "/gettoken",
        "/topapi/calendar/v2/event/create",
    ]
    assert requests[1].read().decode() == (
        '{"calendar_id":"primary","summary":"完成招生方案","description":"TDL ID: tdl-1",'
        '"start_time":1779298200000,"end_time":1779300000000,'
        '"organizer":{"userid":"owner-1"},"attendees":[{"userid":"user-2"}]}'
    )