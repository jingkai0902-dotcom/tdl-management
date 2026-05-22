#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import get_settings  # noqa: E402
from app.integrations.dingtalk_client import DingTalkClient  # noqa: E402


DEFAULT_TITLE = "R5入口测试"
DEFAULT_ENTRY_URL = "https://libu-h5.bdteach.cn/tdl/"


def _default_entry_url() -> str:
    settings = get_settings()
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/") + "/"
    return DEFAULT_ENTRY_URL


def build_message_text(entry_url: str) -> str:
    return "\n".join(
        [
            "## R5入口测试",
            "",
            "这是一条工作通知入口验证消息。",
            "",
            f"[TDL 管理助手入口]({entry_url})",
            "",
            "请在钉钉客户端点击上面的入口链接，确认是否打开 TDL 管理助手网页入口。",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send or preview a DingTalk work notification for R5 entry verification.",
    )
    parser.add_argument(
        "--user-id",
        action="append",
        dest="user_ids",
        required=True,
        help="DingTalk user ID to receive the test notification. Repeat for multiple users.",
    )
    parser.add_argument(
        "--entry-url",
        default=_default_entry_url(),
        help="TDL web entry URL to include in the notification.",
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="DingTalk work notification title.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the notification. Without this flag the script prints a dry run preview.",
    )
    return parser.parse_args(argv)


async def _send_notification(args: argparse.Namespace, *, client: DingTalkClient | None = None) -> None:
    resolved_client = client or DingTalkClient()
    try:
        await resolved_client.send_work_markdown(
            user_ids=args.user_ids,
            title=args.title,
            text=build_message_text(args.entry_url),
        )
    finally:
        if client is None:
            await resolved_client.close()


async def run(args: argparse.Namespace) -> int:
    text = build_message_text(args.entry_url)
    if not args.send:
        print("dry_run=True")
        print(f"user_ids={','.join(args.user_ids)}")
        print(f"title={args.title}")
        print(f"entry_url={args.entry_url}")
        print("")
        print(text)
        return 0

    await _send_notification(args)
    print(f"sent=True user_ids={','.join(args.user_ids)} title={args.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
