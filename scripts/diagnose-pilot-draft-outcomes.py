#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import AuditLog, IntakeDiffLog, TDL  # noqa: E402

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DRAFT_ACTIONS = {"draft_created", "confirmed", "canceled", "draft_updated"}
AUDIT_DRAFT_ACTIONS = {"draft_create", "confirm", "cancel"}


@dataclass(frozen=True)
class DraftOutcome:
    tdl_id: str
    title: str
    status: str
    outcome: str
    owner_id: str | None
    due_at: datetime | None
    completion_criteria: str | None
    cancel_reason: str | None
    created_by: str
    created_at: datetime | None
    raw_text: str | None
    actions: tuple[str, ...]

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing = []
        if not self.owner_id:
            missing.append("owner_id")
        if self.due_at is None:
            missing.append("due_at")
        if not self.completion_criteria:
            missing.append("completion_criteria")
        return tuple(missing)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def default_period(today: date | None = None) -> tuple[datetime, datetime]:
    resolved_today = today or datetime.now(tz=SHANGHAI_TZ).date()
    period_start_date = resolved_today - timedelta(days=resolved_today.weekday())
    period_end_date = resolved_today + timedelta(days=1)
    return (
        datetime.combine(period_start_date, time.min, tzinfo=SHANGHAI_TZ),
        datetime.combine(period_end_date, time.min, tzinfo=SHANGHAI_TZ),
    )


def classify_outcome(tdl: TDL, actions: list[str]) -> str:
    if "canceled" in actions or "cancel" in actions or tdl.status == "canceled":
        if "confirmed" in actions or "confirm" in actions:
            return "confirmed_then_canceled"
        return "canceled"
    if "confirmed" in actions or "confirm" in actions:
        return "confirmed"
    if tdl.status == "draft":
        return "still_draft"
    return "activated_without_confirm"


def build_draft_outcomes(
    tdls: list[TDL],
    diff_logs: list[IntakeDiffLog],
    audit_logs: list[AuditLog],
) -> list[DraftOutcome]:
    diff_by_tdl: dict[str, list[IntakeDiffLog]] = defaultdict(list)
    audit_by_tdl: dict[str, list[AuditLog]] = defaultdict(list)
    draft_tdl_ids: set[str] = set()

    for log in diff_logs:
        if log.tdl_id is None:
            continue
        tdl_id = str(log.tdl_id)
        diff_by_tdl[tdl_id].append(log)
        if log.action_type == "draft_created":
            draft_tdl_ids.add(tdl_id)

    for audit in audit_logs:
        tdl_id = str(audit.entity_id)
        audit_by_tdl[tdl_id].append(audit)
        if audit.action == "draft_create":
            draft_tdl_ids.add(tdl_id)

    tdl_by_id = {str(tdl.tdl_id): tdl for tdl in tdls}
    outcomes = []
    for tdl_id in sorted(draft_tdl_ids):
        tdl = tdl_by_id.get(tdl_id)
        if tdl is None:
            continue
        diff_actions = [log.action_type for log in diff_by_tdl.get(tdl_id, [])]
        audit_actions = [audit.action for audit in audit_by_tdl.get(tdl_id, [])]
        actions = [*diff_actions, *audit_actions]
        raw_text = next(
            (log.raw_text for log in diff_by_tdl.get(tdl_id, []) if log.raw_text),
            None,
        )
        outcomes.append(
            DraftOutcome(
                tdl_id=tdl_id,
                title=tdl.title,
                status=tdl.status,
                outcome=classify_outcome(tdl, actions),
                owner_id=tdl.owner_id,
                due_at=tdl.due_at,
                completion_criteria=tdl.completion_criteria,
                cancel_reason=tdl.cancel_reason,
                created_by=tdl.created_by,
                created_at=tdl.created_at,
                raw_text=raw_text,
                actions=tuple(actions),
            )
        )
    return outcomes


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")


def _clip(value: str | None, limit: int = 42) -> str:
    if not value:
        return "-"
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}..."


def render_draft_outcomes(outcomes: list[DraftOutcome]) -> str:
    outcome_counts = Counter(item.outcome for item in outcomes)
    missing_counts = Counter(
        field_name
        for item in outcomes
        for field_name in item.missing_fields
        if item.outcome in {"canceled", "still_draft"}
    )
    lines = [
        "# Pilot Draft Outcome Diagnosis",
        "",
        f"- Drafts sampled: {len(outcomes)}",
        "- Outcomes: "
        + (
            " / ".join(f"{name} {count}" for name, count in sorted(outcome_counts.items()))
            if outcome_counts
            else "none"
        ),
        "- Missing fields among canceled/still_draft: "
        + (
            " / ".join(f"{name} {count}" for name, count in sorted(missing_counts.items()))
            if missing_counts
            else "none"
        ),
        "",
        "| TDL ID | Outcome | Status | Cancel reason | Created | Owner | Due | Missing | Title | Raw text | Actions |",
        "|---|---|---|---|---:|---|---:|---|---|---|---|",
    ]
    for item in sorted(outcomes, key=lambda draft: (draft.created_at is None, draft.created_at)):
        lines.append(
            "| "
            + " | ".join(
                [
                    item.tdl_id,
                    item.outcome,
                    item.status,
                    item.cancel_reason or "-",
                    _format_dt(item.created_at),
                    item.owner_id or "-",
                    _format_dt(item.due_at),
                    ", ".join(item.missing_fields) or "-",
                    _clip(item.title),
                    _clip(item.raw_text),
                    ", ".join(item.actions) or "-",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose pilot draft confirmation and ignore outcomes.",
    )
    parser.add_argument(
        "--date",
        type=_parse_date,
        help=(
            "Shanghai local date to inspect week-to-date through, formatted as YYYY-MM-DD. "
            "Defaults to today."
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
    return default_period(args.date)


async def load_draft_outcomes(
    *,
    period_start: datetime,
    period_end: datetime,
) -> list[DraftOutcome]:
    async with SessionLocal() as session:
        diff_result = await session.execute(
            select(IntakeDiffLog).where(
                IntakeDiffLog.action_type.in_(DRAFT_ACTIONS),
                IntakeDiffLog.created_at >= period_start,
                IntakeDiffLog.created_at < period_end,
            )
        )
        audit_result = await session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "tdl",
                AuditLog.action.in_(AUDIT_DRAFT_ACTIONS),
                AuditLog.created_at >= period_start,
                AuditLog.created_at < period_end,
            )
        )
        diff_logs = list(diff_result.scalars().all())
        audit_logs = list(audit_result.scalars().all())
        tdl_ids = {
            str(log.tdl_id)
            for log in diff_logs
            if log.tdl_id is not None
        } | {str(audit.entity_id) for audit in audit_logs}
        if not tdl_ids:
            return []
        tdl_result = await session.execute(select(TDL).where(TDL.tdl_id.in_(tdl_ids)))
        return build_draft_outcomes(
            list(tdl_result.scalars().all()),
            diff_logs,
            audit_logs,
        )


async def main() -> None:
    args = _parse_args()
    period_start, period_end = _resolve_period(args)
    outcomes = await load_draft_outcomes(
        period_start=period_start,
        period_end=period_end,
    )
    print(render_draft_outcomes(outcomes))


if __name__ == "__main__":
    asyncio.run(main())
