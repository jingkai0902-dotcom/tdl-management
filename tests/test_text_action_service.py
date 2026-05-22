from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.services.text_action_service import (
    handle_text_action_command,
    parse_text_action_command,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _tdl(title: str, *, status: str = "active"):
    return SimpleNamespace(tdl_id=uuid4(), title=title, status=status)


def test_parse_text_action_command_exact_and_with_title() -> None:
    assert parse_text_action_command("完成").action == "complete"
    assert parse_text_action_command("不是我的任务").action == "reject"
    snooze = parse_text_action_command("暂缓：整理续费复盘")
    assert snooze.action == "snooze"
    assert snooze.query == "整理续费复盘"
    next_morning = parse_text_action_command("明早再提醒：整理续费复盘")
    assert next_morning.action == "snooze"
    assert next_morning.query == "整理续费复盘"
    assert parse_text_action_command("今天别吵我").action == "snooze"


@pytest.mark.asyncio
async def test_handle_text_action_completes_single_candidate(monkeypatch) -> None:
    candidate = _tdl("整理续费复盘")

    async def fake_find_actionable_owned_tdls(session, *, owner_id):
        assert owner_id == "user-1"
        return [candidate]

    async def fake_complete_tdl(session, tdl_id, actor_id):
        assert tdl_id == candidate.tdl_id
        assert actor_id == "user-1"
        candidate.status = "done"
        return candidate

    monkeypatch.setattr(
        "app.services.text_action_service.find_actionable_owned_tdls",
        fake_find_actionable_owned_tdls,
    )
    monkeypatch.setattr("app.services.text_action_service.complete_tdl", fake_complete_tdl)

    card = await handle_text_action_command(
        "session",
        actor_id="user-1",
        source_text="完成",
    )

    assert card.title == "已标记完成"
    assert card.body == ["整理续费复盘"]
    assert card.status == "done"


@pytest.mark.asyncio
async def test_handle_text_action_requires_title_when_multiple_candidates(monkeypatch) -> None:
    async def fake_find_actionable_owned_tdls(session, *, owner_id):
        return [_tdl("整理续费复盘"), _tdl("提交月会材料")]

    monkeypatch.setattr(
        "app.services.text_action_service.find_actionable_owned_tdls",
        fake_find_actionable_owned_tdls,
    )

    card = await handle_text_action_command(
        "session",
        actor_id="user-1",
        source_text="完成",
    )

    assert card.title == "需要指定任务"
    assert "整理续费复盘" in "\n".join(card.body)
    assert "例如：完成：任务标题" in card.body[-1]


@pytest.mark.asyncio
async def test_handle_text_action_uses_title_query_for_reject(monkeypatch) -> None:
    keep = _tdl("整理续费复盘")
    target = _tdl("提交月会材料")

    async def fake_find_actionable_owned_tdls(session, *, owner_id):
        return [keep, target]

    async def fake_reject_tdl(session, tdl_id, actor_id, *, reason):
        assert tdl_id == target.tdl_id
        assert reason == "owner_rejected_by_text_command"
        target.status = "rejected"
        return target

    monkeypatch.setattr(
        "app.services.text_action_service.find_actionable_owned_tdls",
        fake_find_actionable_owned_tdls,
    )
    monkeypatch.setattr("app.services.text_action_service.reject_tdl", fake_reject_tdl)

    card = await handle_text_action_command(
        "session",
        actor_id="user-1",
        source_text="不是我的任务：月会材料",
    )

    assert card.title == "已标记为不是我的任务"
    assert card.body == ["提交月会材料"]


@pytest.mark.asyncio
async def test_handle_text_action_snoozes_until_tomorrow_morning(monkeypatch) -> None:
    candidate = _tdl("整理续费复盘")

    async def fake_find_actionable_owned_tdls(session, *, owner_id):
        return [candidate]

    async def fake_snooze_tdl(session, tdl_id, *, snooze_until, actor_id):
        assert snooze_until == datetime(2026, 5, 19, 9, 0, tzinfo=SHANGHAI_TZ)
        candidate.status = "snoozed"
        return candidate

    monkeypatch.setattr(
        "app.services.text_action_service.find_actionable_owned_tdls",
        fake_find_actionable_owned_tdls,
    )
    monkeypatch.setattr("app.services.text_action_service.snooze_tdl", fake_snooze_tdl)

    card = await handle_text_action_command(
        "session",
        actor_id="user-1",
        source_text="暂缓：整理续费复盘",
        now=datetime(2026, 5, 18, 10, 0, tzinfo=SHANGHAI_TZ),
    )

    assert card.title == "已暂缓"
    assert "2026-05-19 09:00" in card.body[-1]
