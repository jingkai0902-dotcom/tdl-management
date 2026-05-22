import pytest

from app.main import app
from app.api.entry import tdl_entry, tdl_entry_home


@pytest.mark.asyncio
async def test_tdl_entry_home_renders_dingtalk_fallback_guidance() -> None:
    response = await tdl_entry_home()
    body = response.body.decode()

    assert response.status_code == 200
    assert "TDL 管理助手" in body
    assert "TDL管理助手" in body
    assert "复制名称" in body
    assert "navigator.clipboard.writeText" in body
    assert "/health" in body


@pytest.mark.asyncio
async def test_tdl_entry_alias_matches_home() -> None:
    home = await tdl_entry_home()
    alias = await tdl_entry()

    assert alias.body == home.body


def test_tdl_entry_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    assert "/" in paths
    assert "/entry" in paths
