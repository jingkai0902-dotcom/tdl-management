from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.integrations.dingtalk_card import build_card_action_id
from app.services.dingtalk_card_callback_service import (
    FOLLOW_UP_SUBMITTERS,
    ONE_CLICK_ACTIONS,
    _default_snooze_until,
    _management_owner_ids,
    handle_tdl_card_callback,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_routes_complete(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_complete_tdl(session, incoming_tdl_id, actor_id):
        assert session == "session"
        assert incoming_tdl_id == tdl_id
        assert actor_id == "user-1"
        return SimpleNamespace(tdl_id=tdl_id, status="done")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "complete", fake_complete_tdl)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("complete", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "complete"
    assert result.tdl_id == str(tdl_id)
    assert result.status == "done"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_treats_repeated_cancel_as_handled(monkeypatch) -> None:
    tdl_id = uuid4()

    class SessionWithCanceledTDL:
        async def get(self, model, incoming_tdl_id):
            assert incoming_tdl_id == tdl_id
            return SimpleNamespace(tdl_id=tdl_id, status="canceled")

    async def fake_cancel_tdl(session, incoming_tdl_id, actor_id):
        raise ValueError("Only draft TDLs can be canceled through draft intake")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "cancel", fake_cancel_tdl)

    result = await handle_tdl_card_callback(
        SessionWithCanceledTDL(),
        action_id=build_card_action_id("cancel", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "cancel"
    assert result.status == "canceled"
    assert "已处理" in result.response_text


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_treats_repeated_confirm_as_handled(monkeypatch) -> None:
    tdl_id = uuid4()

    class SessionWithActiveTDL:
        async def get(self, model, incoming_tdl_id):
            assert incoming_tdl_id == tdl_id
            return SimpleNamespace(tdl_id=tdl_id, status="active")

    async def fake_confirm_tdl(session, incoming_tdl_id, actor_id):
        raise ValueError("Only draft TDLs can be confirmed")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "confirm", fake_confirm_tdl)

    result = await handle_tdl_card_callback(
        SessionWithActiveTDL(),
        action_id=build_card_action_id("confirm", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "confirm"
    assert result.status == "active"
    assert "已处理" in result.response_text


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_treats_repeated_complete_as_handled(monkeypatch) -> None:
    tdl_id = uuid4()

    class SessionWithDoneTDL:
        async def get(self, model, incoming_tdl_id):
            assert incoming_tdl_id == tdl_id
            return SimpleNamespace(tdl_id=tdl_id, status="done")

    async def fake_complete_tdl(session, incoming_tdl_id, actor_id):
        raise ValueError("Only open TDLs can receive lifecycle actions")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "complete", fake_complete_tdl)

    result = await handle_tdl_card_callback(
        SessionWithDoneTDL(),
        action_id=build_card_action_id("complete", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "complete"
    assert result.status == "done"
    assert "已处理" in result.response_text


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_routes_reject(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_reject_tdl(session, incoming_tdl_id, actor_id):
        assert session == "session"
        assert incoming_tdl_id == tdl_id
        assert actor_id == "user-1"
        return SimpleNamespace(tdl_id=tdl_id, title="招生方案终稿", status="rejected")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "reject", fake_reject_tdl)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("reject", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "reject"
    assert result.status == "rejected"
    assert "已标记为不是我的任务" in result.response_text
    assert "招生方案终稿" in result.response_text


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_treats_repeated_reject_as_handled(monkeypatch) -> None:
    tdl_id = uuid4()

    class SessionWithRejectedTDL:
        async def get(self, model, incoming_tdl_id):
            assert incoming_tdl_id == tdl_id
            return SimpleNamespace(tdl_id=tdl_id, status="rejected")

    async def fake_reject_tdl(session, incoming_tdl_id, actor_id):
        raise ValueError("Only open TDLs can receive lifecycle actions")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "reject", fake_reject_tdl)

    result = await handle_tdl_card_callback(
        SessionWithRejectedTDL(),
        action_id=build_card_action_id("reject", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "reject"
    assert result.status == "rejected"
    assert "已处理" in result.response_text


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_returns_permission_feedback(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_complete_tdl(session, incoming_tdl_id, actor_id):
        raise ValueError("Only the current owner can receive lifecycle actions")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "complete", fake_complete_tdl)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("complete", tdl_id),
        actor_id="other-user",
    )

    assert result.handled is False
    assert result.action == "complete"
    assert result.tdl_id == str(tdl_id)
    assert "不能直接操作" in result.response_text


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_returns_missing_fields_feedback(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_confirm_tdl(session, incoming_tdl_id, actor_id):
        raise ValueError("TDL draft missing required fields: owner_id, due_at")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "confirm", fake_confirm_tdl)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("confirm", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is False
    assert result.action == "confirm"
    assert result.tdl_id == str(tdl_id)
    assert result.response_text == "这条草稿还不能确认，请先补负责人和截止时间。"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "expected_feedback"),
    [
        ("owner_id", "这条草稿还不能确认，请先补负责人。"),
        ("due_at", "这条草稿还不能确认，请先补截止时间。"),
    ],
)
async def test_handle_tdl_card_callback_returns_single_missing_field_feedback(
    monkeypatch,
    field_name,
    expected_feedback,
) -> None:
    tdl_id = uuid4()

    async def fake_confirm_tdl(session, incoming_tdl_id, actor_id):
        raise ValueError(f"TDL draft missing required fields: {field_name}")

    monkeypatch.setitem(ONE_CLICK_ACTIONS, "confirm", fake_confirm_tdl)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("confirm", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is False
    assert result.response_text == expected_feedback


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_ignores_actions_needing_extra_input() -> None:
    tdl_id = uuid4()

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("postpone", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is False
    assert result.action == "postpone"
    assert result.tdl_id == str(tdl_id)
    assert result.next_action == "collect_due_at"
    assert result.required_fields == ["due_at"]
    assert result.response_text == "请回复新的截止时间，例如：延期到明天下午六点"


def test_default_snooze_until_uses_tomorrow_morning_shanghai() -> None:
    result = _default_snooze_until(datetime(2026, 5, 19, 23, 30, tzinfo=SHANGHAI_TZ))

    assert result == datetime(2026, 5, 20, 9, 0, tzinfo=SHANGHAI_TZ)


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_returns_owner_follow_up() -> None:
    tdl_id = uuid4()

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_owner", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is False
    assert result.action == "set_owner"
    assert result.next_action == "collect_owner_id"
    assert result.required_fields == ["owner_id"]


def test_management_owner_ids_reads_management_roster() -> None:
    assert "0617564550-1513038363" in _management_owner_ids()


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_valid_owner(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_update_draft_tdl(session, incoming_tdl_id, payload, actor_id):
        assert session == "session"
        assert incoming_tdl_id == tdl_id
        assert actor_id == "user-1"
        assert payload.owner_id == "0617564550-1513038363"
        return SimpleNamespace(tdl_id=tdl_id, status="draft")

    monkeypatch.setattr(
        "app.services.dingtalk_card_callback_service.update_draft_tdl",
        fake_update_draft_tdl,
    )

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_owner", tdl_id),
        actor_id="user-1",
        submitted_fields={"owner_id": "0617564550-1513038363"},
    )

    assert result.handled is True
    assert result.status == "draft"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_rejects_owner_outside_roster() -> None:
    tdl_id = uuid4()

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_owner", tdl_id),
        actor_id="user-1",
        submitted_fields={"owner_id": "outsider"},
    )

    assert result.handled is False
    assert result.next_action == "collect_owner_id"
    assert result.response_text == "请回复负责人，例如：负责人改成李珍"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_set_due_at(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.due_at.isoformat() == "2026-05-31T18:00:00+08:00"
        return SimpleNamespace(tdl_id=tdl_id, status="draft")

    monkeypatch.setitem(FOLLOW_UP_SUBMITTERS, "set_due_at", fake_submitter)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_due_at", tdl_id),
        actor_id="user-1",
        submitted_fields={"due_at": "2026-05-31T18:00:00+08:00"},
    )

    assert result.handled is True
    assert result.action == "set_due_at"
    assert result.tdl_id == str(tdl_id)
    assert result.status == "draft"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_prompts_when_due_at_invalid() -> None:
    tdl_id = uuid4()

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_due_at", tdl_id),
        actor_id="user-1",
        submitted_fields={"due_at": "not-a-date"},
    )

    assert result.handled is False
    assert result.next_action == "collect_due_at"
    assert result.response_text == "请回复截止时间，例如：改到明天下午六点"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_postpone(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.due_at.isoformat() == "2026-06-02T18:00:00+08:00"
        return SimpleNamespace(tdl_id=tdl_id, status="active")

    monkeypatch.setitem(FOLLOW_UP_SUBMITTERS, "postpone", fake_submitter)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("postpone", tdl_id),
        actor_id="user-1",
        submitted_fields={"due_at": "2026-06-02T18:00:00+08:00"},
    )

    assert result.handled is True
    assert result.status == "active"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_snooze(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.snooze_until.isoformat() == "2026-05-20T09:00:00+08:00"
        return SimpleNamespace(tdl_id=tdl_id, title="招生方案终稿", status="snoozed")

    monkeypatch.setitem(FOLLOW_UP_SUBMITTERS, "snooze", fake_submitter)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("snooze", tdl_id),
        actor_id="user-1",
        submitted_fields={"snooze_until": "2026-05-20T09:00:00+08:00"},
    )

    assert result.handled is True
    assert result.status == "snoozed"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_defaults_snooze_without_submitted_time(monkeypatch) -> None:
    tdl_id = uuid4()
    captured_snooze_until = None

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        nonlocal captured_snooze_until
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.snooze_until is not None
        captured_snooze_until = submission.snooze_until
        return SimpleNamespace(tdl_id=tdl_id, title="招生方案终稿", status="snoozed")

    monkeypatch.setitem(FOLLOW_UP_SUBMITTERS, "snooze", fake_submitter)

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("snooze", tdl_id),
        actor_id="user-1",
    )

    assert result.handled is True
    assert result.action == "snooze"
    assert result.status == "snoozed"
    assert "已暂缓" in result.response_text
    assert "招生方案终稿" in result.response_text
    assert f"下次提醒：{captured_snooze_until:%Y-%m-%d %H:%M}" in result.response_text


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_submits_completion_criteria(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_submitter(session, *, tdl_id, actor_id, submission):
        assert session == "session"
        assert actor_id == "user-1"
        assert submission.completion_criteria == "形成可执行课表"
        return SimpleNamespace(tdl_id=tdl_id, status="draft")

    monkeypatch.setitem(
        FOLLOW_UP_SUBMITTERS,
        "set_completion_criteria",
        fake_submitter,
    )

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_completion_criteria", tdl_id),
        actor_id="user-1",
        submitted_fields={"completion_criteria": "形成可执行课表"},
    )

    assert result.handled is True
    assert result.action == "set_completion_criteria"
    assert result.status == "draft"


@pytest.mark.asyncio
async def test_handle_tdl_card_callback_prompts_when_completion_criteria_empty() -> None:
    tdl_id = uuid4()

    result = await handle_tdl_card_callback(
        "session",
        action_id=build_card_action_id("set_completion_criteria", tdl_id),
        actor_id="user-1",
        submitted_fields={"completion_criteria": ""},
    )

    assert result.handled is False
    assert result.next_action == "collect_completion_criteria"
    assert result.response_text == "请回复完成标准，例如：完成标准是列出三条动作"
