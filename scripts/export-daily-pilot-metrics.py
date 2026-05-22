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
    parser.add_argument(
        "--append-ledger",
        type=Path,
        help="Append or replace the dated auto-export block in this Markdown ledger.",
    )
    return parser.parse_args()


def _resolve_period(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.period_start or args.period_end:
        if not args.period_start or not args.period_end:
            raise SystemExit("--period-start and --period-end must be provided together")
        return args.period_start, args.period_end
    return _default_period(args.date)


def _ledger_date(args: argparse.Namespace, period_end: datetime) -> date:
    if args.date is not None:
        return args.date
    return (period_end.astimezone(SHANGHAI_TZ) - timedelta(days=1)).date()


def append_ledger(path: Path, rendered: str, *, entry_date: date) -> None:
    auto_heading = "## 自动导出记录"
    marker = entry_date.isoformat()
    begin = f"<!-- pilot-metrics:{marker}:begin -->"
    end = f"<!-- pilot-metrics:{marker}:end -->"
    block = "\n".join(
        [
            begin,
            f"### {marker} 自动导出",
            "",
            rendered.rstrip(),
            end,
            "",
        ]
    )
    original = path.read_text(encoding="utf-8") if path.exists() else "# Daily Pilot Metrics\n"
    if begin in original and end in original:
        prefix, rest = original.split(begin, 1)
        _, suffix = rest.split(end, 1)
        updated = f"{prefix}{block}{suffix.lstrip()}"
    else:
        separator = "" if original.endswith("\n") else "\n"
        heading = "" if auto_heading in original else f"\n{auto_heading}\n"
        updated = f"{original}{separator}{heading}\n{block}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


async def main() -> None:
    args = _parse_args()
    period_start, period_end = _resolve_period(args)
    async with SessionLocal() as session:
        metrics = await generate_pilot_metrics(
            session,
            period_start=period_start,
            period_end=period_end,
        )
    rendered = render_pilot_metrics_markdown(metrics)
    if args.append_ledger is not None:
        append_ledger(
            args.append_ledger,
            rendered,
            entry_date=_ledger_date(args, period_end),
        )
    else:
        print(rendered)


if __name__ == "__main__":
    asyncio.run(main())
