from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers.intake_queue import process_next_intake_queue_item


class FakeSessionContext:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeDingTalkClient:
    def __init__(self) -> None:
        self.sent_interactive = []
        self.sent_markdown = []
        self.closed = False

    async def send_interactive_card_to_user(self, **kwargs) -> None:
        self.sent_interactive.append(kwargs)

    async def send_work_markdown(self, **kwargs) -> None:
        self.sent_markdown.append(kwargs)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_process_next_intake_queue_item_sends_template_card(monkeypatch) -> None:
    queue_item = SimpleNamespace(
        intake_id=uuid4(),
        message_id="msg-1",
        sender_id="user-1",
        sender_nick="Frank",
        content="下周三前审核暑期班方案",
    )
    client = FakeDingTalkClient()
    seen = {}

    async def fake_claim(session):
        seen["claim_session"] = session
        return queue_item

    async def fake_intake(session, message, ai_client=None):
        seen["message"] = message
        return SimpleNamespace(
            title="TDL 草稿",
            body=["审核暑期班方案"],
            status="draft",
            buttons=[SimpleNamespace(label="确认创建", action="confirm", tdl_id=uuid4())],
        )

    async def fake_mark_done(session, item):
        seen["done"] = (session, item.message_id)

    async def fake_mark_failed(*args, **kwargs):
        raise AssertionError("successful item must not be marked failed")

    state_events = []

    monkeypatch.setattr(
        "app.workers.intake_queue.get_settings",
        lambda: SimpleNamespace(dingtalk_tdl_card_template_id="tpl-1"),
    )
    monkeypatch.setattr("app.workers.intake_queue.claim_next_intake", fake_claim)
    monkeypatch.setattr("app.workers.intake_queue.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr("app.workers.intake_queue.mark_intake_done", fake_mark_done)
    monkeypatch.setattr("app.workers.intake_queue.mark_intake_failed", fake_mark_failed)
    monkeypatch.setattr(
        "app.workers.intake_queue.write_started",
        lambda process_name: state_events.append(("started", process_name)),
    )
    monkeypatch.setattr(
        "app.workers.intake_queue.write_success",
        lambda process_name: state_events.append(("success", process_name)),
    )

    processed = await process_next_intake_queue_item(
        session_factory=FakeSessionContext,
        client_factory=lambda: client,
    )

    assert processed is True
    assert seen["claim_session"] == "session"
    assert seen["message"].message_id == "msg-1"
    assert seen["done"] == ("session", "msg-1")
    assert client.sent_interactive[0]["user_id"] == "user-1"
    assert client.sent_interactive[0]["card_template_id"] == "tpl-1"
    assert client.sent_markdown == []
    assert client.closed is True
    assert state_events == [("started", "intake_worker"), ("success", "intake_worker")]


@pytest.mark.asyncio
async def test_process_next_intake_queue_item_returns_false_when_empty(monkeypatch) -> None:
    async def fake_claim(session):
        return None

    state_events = []

    monkeypatch.setattr("app.workers.intake_queue.claim_next_intake", fake_claim)
    monkeypatch.setattr(
        "app.workers.intake_queue.write_heartbeat",
        lambda process_name: state_events.append(("heartbeat", process_name)),
    )

    processed = await process_next_intake_queue_item(session_factory=FakeSessionContext)

    assert processed is False
    assert state_events == [("heartbeat", "intake_worker")]


@pytest.mark.asyncio
async def test_process_next_intake_queue_item_marks_failure(monkeypatch) -> None:
    queue_item = SimpleNamespace(
        intake_id=uuid4(),
        message_id="msg-fail",
        sender_id="user-1",
        sender_nick="Frank",
        content="下周三前审核暑期班方案",
    )
    seen = {}

    async def fake_claim(session):
        return queue_item

    async def fake_intake(*args, **kwargs):
        raise RuntimeError("provider down")

    async def fake_mark_failed(session, item, *, error):
        seen["failed"] = (session, item.message_id, str(error))

    state_events = []

    monkeypatch.setattr("app.workers.intake_queue.claim_next_intake", fake_claim)
    monkeypatch.setattr("app.workers.intake_queue.intake_dingtalk_message", fake_intake)
    monkeypatch.setattr("app.workers.intake_queue.mark_intake_failed", fake_mark_failed)
    monkeypatch.setattr(
        "app.workers.intake_queue.write_started",
        lambda process_name: state_events.append(("started", process_name)),
    )
    monkeypatch.setattr(
        "app.workers.intake_queue.write_failure",
        lambda process_name, error, *, stop_signal: state_events.append(
            ("failure", process_name, str(error), stop_signal)
        ),
    )

    with pytest.raises(RuntimeError, match="provider down"):
        await process_next_intake_queue_item(session_factory=FakeSessionContext)

    assert seen["failed"] == ("session", "msg-fail", "provider down")
    assert state_events == [
        ("started", "intake_worker"),
        ("failure", "intake_worker", "provider down", "intake_worker_item_failed"),
    ]
