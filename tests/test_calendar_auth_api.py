import pytest
from fastapi import HTTPException

from app.api import calendar_auth


class FakeSession:
    pass


@pytest.mark.asyncio
async def test_calendar_auth_callback_stores_matching_user(monkeypatch) -> None:
    stored = {}

    class FakeDingTalkClient:
        async def exchange_user_authorization_code(self, code: str):
            assert code == "auth-code"
            return {
                "accessToken": "access-1",
                "refreshToken": "refresh-1",
                "expireIn": 7200,
            }

        async def get_current_user_profile(self, access_token: str):
            assert access_token == "access-1"
            return {"unionId": "union-1"}

        async def get_user_id_by_union_id(self, union_id: str):
            assert union_id == "union-1"
            return "user-1"

        async def close(self):
            return None

    async def fake_store_calendar_authorization(session, **kwargs):
        stored.update(kwargs)

    monkeypatch.setattr(calendar_auth, "DingTalkClient", FakeDingTalkClient)
    monkeypatch.setattr(calendar_auth, "parse_calendar_auth_state", lambda state: "user-1")
    monkeypatch.setattr(
        calendar_auth,
        "store_calendar_authorization",
        fake_store_calendar_authorization,
    )

    response = await calendar_auth.finish_calendar_authorization(
        state="state-1",
        auth_code="auth-code",
        session=FakeSession(),
    )

    assert response.body.decode() == "日历同步已开通，可以关闭这个页面。"
    assert stored["dingtalk_user_id"] == "user-1"
    assert stored["union_id"] == "union-1"


@pytest.mark.asyncio
async def test_calendar_auth_callback_rejects_mismatched_user(monkeypatch) -> None:
    class FakeDingTalkClient:
        async def exchange_user_authorization_code(self, code: str):
            return {
                "accessToken": "access-1",
                "refreshToken": "refresh-1",
                "expireIn": 7200,
            }

        async def get_current_user_profile(self, access_token: str):
            return {"unionId": "union-1"}

        async def get_user_id_by_union_id(self, union_id: str):
            return "other-user"

        async def close(self):
            return None

    monkeypatch.setattr(calendar_auth, "DingTalkClient", FakeDingTalkClient)
    monkeypatch.setattr(calendar_auth, "parse_calendar_auth_state", lambda state: "user-1")

    with pytest.raises(HTTPException) as exc:
        await calendar_auth.finish_calendar_authorization(
            state="state-1",
            auth_code="auth-code",
            session=FakeSession(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Calendar authorization account does not match requested user"
