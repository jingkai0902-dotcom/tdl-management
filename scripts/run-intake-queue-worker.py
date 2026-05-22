#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.workers.intake_queue import process_next_intake_queue_item  # noqa: E402


async def _run(*, once: bool, poll_interval: float) -> None:
    while True:
        processed = await process_next_intake_queue_item()
        if once:
            return
        if not processed:
            await asyncio.sleep(poll_interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TDL intake queue worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued item and exit.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="Seconds to wait between empty queue polls.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(once=args.once, poll_interval=args.poll_interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
