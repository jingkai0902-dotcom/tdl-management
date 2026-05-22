#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services.pilot_metrics_service import (  # noqa: E402
    generate_pilot_metrics,
    render_pilot_metrics_markdown,
)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _default_period(today: date | None = None) -> tuple[datetime, datetime]:
    resolved_today = today or datetime.now(tz=SHANGHAI_TZ).date()
    period_start_date = resolved_today - timedelta(days=resolved_today.weekday())
    period_end_date = resolved_today + timedelta(days=1)
    return (
        datetime.combine(period_start_date, time.min, tzinfo=SHANGHAI_TZ),
        datetime.combine(period_end_date, time.min, tzinfo=SHANGHAI_TZ),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export daily pilot metrics as Markdown.",
    )
    parser.add_argument(
        "--date",
        type=_parse_date,
        help=(
            "Shanghai local date to export week-to-date metrics through, "
            "formatted as YYYY-MM-DD. Defaults to today."
        ),
    )
    parser.add_argument(
        "--period-start",
        type=datetime.fromisoformat,
        help="Inclusive period start. Overrides --date when paired with --period-end.",
    )
    parser.add_argument(
        "--period-end",
        type=datetime.fromisoformat,
        help="Exclusive period end. Overrides --date when paired with --period-start.",
    )
    return parser.parse_args()


def _resolve_period(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.period_start or args.period_end:
        if not args.period_start or not args.period_end:
            raise SystemExit("--period-start and --period-end must be provided together")
        return args.period_start, args.period_end
    return _default_period(args.date)


async def main() -> None:
    args = _parse_args()
    period_start, period_end = _resolve_period(args)
    async with SessionLocal() as session:
        metrics = await generate_pilot_metrics(
            session,
            period_start=period_start,
            period_end=period_end,
        )
    print(render_pilot_metrics_markdown(metrics))


if __name__ == "__main__":
    asyncio.run(main())
