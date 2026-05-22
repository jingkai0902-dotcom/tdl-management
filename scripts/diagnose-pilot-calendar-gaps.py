#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

from sqlalchemy import select


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import AuditLog, TDL  # noqa: E402
from app.services.pilot_metrics_service import OPEN_STATUSES  # noqa: E402


CALENDAR_AUDIT_ACTIONS = {
    "calendar_authorization_required",
    "calendar_create",
    "calendar_create_failed",
    "calendar_update",
    "calendar_update_failed",
}


@dataclass(frozen=True)
class CalendarGap:
    tdl_id: str
    status: str
    title: str
    owner_id: str | None
    due_at: str | None
    source: str
    latest_calendar_action: str | None
    reason: str


def classify_calendar_gap(tdl: TDL, audits: list[AuditLog]) -> CalendarGap:
    latest = audits[-1] if audits else None
    error = str((latest.payload or {}).get("error", "")) if latest else ""
    reason = "no_calendar_attempt"
    if latest is not None:
        if latest.action == "calendar_authorization_required":
            reason = "missing_user_authorization"
        elif "qyapi_calendar_create" in error or "应用尚未开通所需的权限" in error:
            reason = "app_calendar_scope_missing_at_attempt"
        elif "authCode.notFound" in error:
            reason = "invalid_or_expired_auth_code"
        elif "can not be parsed correctly" in error:
            reason = "invalid_calendar_user_identifier"
        elif "Unknown reminder method" in error:
            reason = "calendar_payload_reminder_method_rejected"
        elif latest.action and latest.action.endswith("_failed"):
            reason = "calendar_api_error"
    elif not tdl.owner_id or not tdl.due_at:
        reason = "missing_owner_or_due_at"

    return CalendarGap(
        tdl_id=str(tdl.tdl_id),
        status=tdl.status,
        title=tdl.title,
        owner_id=tdl.owner_id,
        due_at=tdl.due_at.isoformat() if tdl.due_at else None,
        source=tdl.source,
        latest_calendar_action=latest.action if latest else None,
        reason=reason,
    )


def render_calendar_gaps(gaps: list[CalendarGap]) -> str:
    lines = [
        "# Pilot Calendar Gaps",
        "",
        f"- Missing calendar events: {len(gaps)}",
        "",
        "| Reason | Status | Owner | Due At | Source | Title | TDL ID |",
        "|---|---|---|---|---|---|---|",
    ]
    for gap in gaps:
        lines.append(
            "| "
            f"{gap.reason} | "
            f"{gap.status} | "
            f"{gap.owner_id or 'N/A'} | "
            f"{gap.due_at or 'N/A'} | "
            f"{gap.source} | "
            f"{gap.title} | "
            f"{gap.tdl_id} |"
        )
    return "\n".join(lines)


async def load_calendar_gaps() -> list[CalendarGap]:
    async with SessionLocal() as session:
        tdl_result = await session.execute(
            select(TDL)
            .where(
                TDL.status.in_(OPEN_STATUSES),
                TDL.calendar_event_id.is_(None),
            )
            .order_by(TDL.created_at)
        )
        gaps = []
        for tdl in tdl_result.scalars().all():
            audit_result = await session.execute(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "tdl",
                    AuditLog.entity_id == str(tdl.tdl_id),
                    AuditLog.action.in_(CALENDAR_AUDIT_ACTIONS),
                )
                .order_by(AuditLog.created_at)
            )
            gaps.append(classify_calendar_gap(tdl, list(audit_result.scalars().all())))
        return gaps


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose open TDLs that do not have DingTalk calendar events.",
    )
    parser.add_argument(
        "--fail-on-gaps",
        action="store_true",
        help="Exit with status 1 when any open TDL is missing a calendar event.",
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    gaps = await load_calendar_gaps()
    print(render_calendar_gaps(gaps))
    return 1 if args.fail_on_gaps and gaps else 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
