from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "send-r5-entry-test-notification.py"
SPEC = importlib.util.spec_from_file_location("send_r5_entry_test_notification", SCRIPT_PATH)
assert SPEC is not None
SCRIPT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SCRIPT)


def test_build_message_text_includes_entry_link() -> None:
    text = SCRIPT.build_message_text("https://example.test/tdl/")

    assert "## R5入口测试" in text
    assert "[TDL 管理助手入口](https://example.test/tdl/)" in text
    assert "确认是否打开 TDL 管理助手网页入口" in text


def test_parse_args_defaults_to_dry_run() -> None:
    args = SCRIPT.parse_args(["--user-id", "user-1", "--entry-url", "https://example.test/tdl/"])

    assert args.user_ids == ["user-1"]
    assert args.entry_url == "https://example.test/tdl/"
    assert args.title == "R5入口测试"
    assert args.send is False


@pytest.mark.asyncio
async def test_run_dry_run_prints_preview_without_sending(capsys: pytest.CaptureFixture[str]) -> None:
    args = argparse.Namespace(
        user_ids=["user-1"],
        entry_url="https://example.test/tdl/",
        title="R5入口测试",
        send=False,
    )

    result = await SCRIPT.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "dry_run=True" in output
    assert "user_ids=user-1" in output
    assert "[TDL 管理助手入口](https://example.test/tdl/)" in output


@pytest.mark.asyncio
async def test_send_notification_uses_work_markdown() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        async def send_work_markdown(self, **kwargs) -> None:
            self.calls.append(kwargs)

    args = argparse.Namespace(
        user_ids=["user-1"],
        entry_url="https://example.test/tdl/",
        title="R5入口测试",
        send=True,
    )
    client = FakeClient()

    await SCRIPT._send_notification(args, client=client)

    assert client.calls == [
        {
            "user_ids": ["user-1"],
            "title": "R5入口测试",
            "text": SCRIPT.build_message_text("https://example.test/tdl/"),
        }
    ]
