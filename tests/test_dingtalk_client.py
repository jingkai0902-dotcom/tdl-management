import httpx
import pytest

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
