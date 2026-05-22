from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "send-calendar-auth-reminder.py"
SPEC = importlib.util.spec_from_file_location("send_calendar_auth_reminder", SCRIPT_PATH)
assert SPEC is not None
SCRIPT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SCRIPT
SPEC.loader.exec_module(SCRIPT)


def test_build_message_text_includes_authorization_link(monkeypatch) -> None:
    monkeypatch.setattr(
        SCRIPT,
        "build_calendar_auth_start_url",
        lambda user_id: f"https://example.test/calendar/auth/start?user_id={user_id}",
    )

    text = SCRIPT.build_message_text("user-1")

    assert "## 开通 TDL 日历同步" in text
    assert "[开通我的日历同步](https://example.test/calendar/auth/start?user_id=user-1)" in text


def test_parse_args_defaults_to_dry_run() -> None:
    args = SCRIPT.parse_args(["--user-id", "user-1"])

    assert args.user_id == "user-1"
    assert args.title == "开通 TDL 日历同步"
    assert args.send is False


@pytest.mark.asyncio
async def test_run_dry_run_prints_preview_without_sending(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        SCRIPT,
        "build_calendar_auth_start_url",
        lambda user_id: f"https://example.test/calendar/auth/start?user_id={user_id}",
    )
    args = argparse.Namespace(user_id="user-1", title="开通 TDL 日历同步", send=False)

    result = await SCRIPT.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "dry_run=True" in output
    assert "user_id=user-1" in output
    assert "https://example.test/calendar/auth/start?user_id=user-1" in output


@pytest.mark.asyncio
async def test_send_reminder_uses_work_markdown(monkeypatch) -> None:
    monkeypatch.setattr(
        SCRIPT,
        "build_calendar_auth_start_url",
        lambda user_id: f"https://example.test/calendar/auth/start?user_id={user_id}",
    )

    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        async def send_work_markdown(self, **kwargs) -> None:
            self.calls.append(kwargs)

    args = argparse.Namespace(user_id="user-1", title="开通 TDL 日历同步", send=True)
    client = FakeClient()

    await SCRIPT._send_reminder(args, client=client)

    assert client.calls == [
        {
            "user_ids": ["user-1"],
            "title": "开通 TDL 日历同步",
            "text": SCRIPT.build_message_text("user-1"),
        }
    ]
