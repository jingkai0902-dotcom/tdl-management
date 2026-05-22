#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.integrations.dingtalk_client import DingTalkClient  # noqa: E402
from app.services.calendar_auth_service import build_calendar_auth_start_url  # noqa: E402


DEFAULT_TITLE = "开通 TDL 日历同步"


def build_message_text(user_id: str) -> str:
    auth_url = build_calendar_auth_start_url(user_id)
    return "\n".join(
        [
            "## 开通 TDL 日历同步",
            "",
            "为了把你的 TDL 自动写入钉钉日历，需要先完成一次授权。",
            "",
            f"[开通我的日历同步]({auth_url})",
            "",
            "授权完成后，新确认的 TDL 会自动尝试写入你的钉钉日历。",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send or preview a DingTalk calendar authorization reminder.",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="DingTalk user ID that should authorize calendar sync.",
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="DingTalk work notification title.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the reminder. Without this flag the script prints a dry run preview.",
    )
    return parser.parse_args(argv)


async def _send_reminder(args: argparse.Namespace, *, client: DingTalkClient | None = None) -> None:
    resolved_client = client or DingTalkClient()
    try:
        await resolved_client.send_work_markdown(
            user_ids=[args.user_id],
            title=args.title,
            text=build_message_text(args.user_id),
        )
    finally:
        if client is None:
            await resolved_client.close()


async def run(args: argparse.Namespace) -> int:
    text = build_message_text(args.user_id)
    if not args.send:
        print("dry_run=True")
        print(f"user_id={args.user_id}")
        print(f"title={args.title}")
        print("")
        print(text)
        return 0

    await _send_reminder(args)
    print(f"sent=True user_id={args.user_id} title={args.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
