from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models import CalendarAuthorization
from app.services.calendar_auth_service import (
    build_calendar_auth_state,
    get_valid_calendar_authorization,
    parse_calendar_auth_state,
    store_calendar_authorization,
)


class FakeSession:
    def __init__(self, authorization: CalendarAuthorization | None = None) -> None:
        self.authorization = authorization
        self.added = []

    async def get(self, model, identifier):
        if self.authorization and self.authorization.dingtalk_user_id == identifier:
            return self.authorization
        return None

    def add(self, item):
        self.added.append(item)
        self.authorization = item

    async def commit(self):
        return None

    async def refresh(self, item):
        return None


def test_calendar_auth_state_round_trips(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.calendar_auth_service._management_user_ids",
        lambda: {"user-1"},
    )
    monkeypatch.setattr(
        "app.services.calendar_auth_service._state_secret",
        lambda: b"secret",
    )
    now = datetime(2026, 5, 16, 8, 0, tzinfo=UTC)
    state = build_calendar_auth_state("user-1", now=now)

    assert parse_calendar_auth_state(state, now=now + timedelta(minutes=10)) == "user-1"


def test_calendar_auth_state_rejects_expired_tokens(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.calendar_auth_service._management_user_ids",
        lambda: {"user-1"},
    )
    monkeypatch.setattr(
        "app.services.calendar_auth_service._state_secret",
        lambda: b"secret",
    )
    now = datetime(2026, 5, 16, 8, 0, tzinfo=UTC)
    state = build_calendar_auth_state("user-1", now=now)

    with pytest.raises(ValueError, match="Invalid calendar auth state"):
        parse_calendar_auth_state(state, now=now + timedelta(minutes=16))


@pytest.mark.asyncio
async def test_store_calendar_authorization_upserts_tokens() -> None:
    session = FakeSession()
    now = datetime(2026, 5, 16, 8, 0, tzinfo=UTC)

    authorization = await store_calendar_authorization(
        session,
        dingtalk_user_id="user-1",
        union_id="union-1",
        token_payload={
            "accessToken": "access-1",
            "refreshToken": "refresh-1",
            "expireIn": 7200,
            "refreshTokenExpireIn": 2592000,
            "scope": "openid",
        },
        now=now,
    )

    assert authorization.access_token == "access-1"
    assert authorization.access_token_expires_at == now + timedelta(seconds=7200)
    assert authorization.refresh_token_expires_at == now + timedelta(seconds=2592000)


@pytest.mark.asyncio
async def test_get_valid_calendar_authorization_refreshes_expired_tokens() -> None:
    now = datetime(2026, 5, 16, 8, 0, tzinfo=UTC)
    authorization = CalendarAuthorization(
        dingtalk_user_id="user-1",
        union_id="union-1",
        access_token="old-access",
        refresh_token="old-refresh",
        access_token_expires_at=now - timedelta(minutes=1),
        refresh_token_expires_at=now + timedelta(days=1),
    )
    session = FakeSession(authorization)

    class FakeDingTalkClient:
        async def refresh_user_access_token(self, refresh_token: str):
            assert refresh_token == "old-refresh"
            return {
                "accessToken": "new-access",
                "refreshToken": "new-refresh",
                "expireIn": 7200,
            }

    refreshed = await get_valid_calendar_authorization(
        session,
        dingtalk_user_id="user-1",
        client=FakeDingTalkClient(),
        now=now,
    )

    assert refreshed.access_token == "new-access"
    assert refreshed.refresh_token == "new-refresh"
