#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys
from uuid import UUID

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import AuditLog, TDL  # noqa: E402


CLEANUP_ACTOR_ID = "codex"
CLEANUP_REASON = "pilot_test_residual_cleanup"
CLEANUP_AUDIT_ACTION = "pilot_cleanup_cancel"


@dataclass(frozen=True)
class CleanupCandidate:
    tdl_id: str
    title: str
    reason: str


TEST_RESIDUAL_CANDIDATES: tuple[CleanupCandidate, ...] = (
    CleanupCandidate(
        "bd4434a0-3c9b-4f03-a1c4-0df566b1144a",
        "日历同步联调测试",
        "manual calendar integration test",
    ),
    CleanupCandidate(
        "0d8beb4a-8815-4de2-81c4-b0ee696a6ed1",
        "完成日历同步验证",
        "calendar integration verification",
    ),
    CleanupCandidate(
        "15ea9f17-740f-4b7a-8b77-a36652bfbdae",
        "测试日历联动",
        "calendar integration test",
    ),
    CleanupCandidate(
        "8498bd5f-47e2-4e72-9704-a02b4578d3f5",
        "向李祯提交今日工作总结并请其审阅反馈",
        "old owner typo test sample",
    ),
    CleanupCandidate(
        "fea1a5a6-a699-4c0c-bf23-da3f1781a1af",
        "将姓名更正为李珍（珍珠的珍），即 Helen",
        "old correction false-positive sample",
    ),
    CleanupCandidate(
        "0fa465cf-8461-4c32-8612-682af2f403e1",
        "【Codex真实按钮测试-暂缓】请点击暂缓",
        "live button test",
    ),
    CleanupCandidate(
        "8285fa28-1228-4a23-9995-7112ef8e8e71",
        "完成 Codex 草稿模板卡 D1 复测",
        "Codex draft card test",
    ),
    CleanupCandidate(
        "d7812381-6ed3-48e4-81da-6ae24c3b8c83",
        "完成Codex A2暂缓测试",
        "Codex snooze test",
    ),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cancel explicit pilot test residuals from the attention backlog.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply cleanup. Without this flag the script only prints a dry-run report.",
    )
    return parser.parse_args(argv)


async def cleanup_attention_backlog(*, execute: bool) -> int:
    async with SessionLocal() as session:
        result = await session.execute(
            select(TDL).where(
                TDL.tdl_id.in_([UUID(candidate.tdl_id) for candidate in TEST_RESIDUAL_CANDIDATES])
            )
        )
        tdls_by_id = {str(tdl.tdl_id): tdl for tdl in result.scalars().all()}

        errors: list[str] = []
        matched: list[tuple[CleanupCandidate, TDL]] = []
        for candidate in TEST_RESIDUAL_CANDIDATES:
            tdl = tdls_by_id.get(candidate.tdl_id)
            if tdl is None:
                errors.append(f"missing | {candidate.tdl_id} | {candidate.title}")
                continue
            if tdl.title != candidate.title:
                errors.append(
                    f"title_mismatch | {candidate.tdl_id} | expected={candidate.title} | actual={tdl.title}"
                )
                continue
            if tdl.status != "attention":
                errors.append(
                    f"status_mismatch | {candidate.tdl_id} | expected=attention | actual={tdl.status}"
                )
                continue
            matched.append((candidate, tdl))

        print(f"dry_run={not execute}")
        print(f"expected={len(TEST_RESIDUAL_CANDIDATES)} matched={len(matched)} errors={len(errors)}")
        for candidate, tdl in matched:
            print(
                f"candidate | {tdl.tdl_id} | {tdl.status} -> canceled | "
                f"{candidate.reason} | {tdl.title}"
            )
        for error in errors:
            print(f"error | {error}")

        if errors:
            return 1
        if not execute:
            return 0

        for candidate, tdl in matched:
            previous_status = tdl.status
            tdl.status = "canceled"
            tdl.cancel_reason = CLEANUP_REASON
            session.add(
                AuditLog(
                    entity_type="tdl",
                    entity_id=str(tdl.tdl_id),
                    action=CLEANUP_AUDIT_ACTION,
                    actor_id=CLEANUP_ACTOR_ID,
                    payload={
                        "reason": CLEANUP_REASON,
                        "previous_status": previous_status,
                        "classification": "test_residual",
                        "classification_reason": candidate.reason,
                    },
                )
            )
        await session.commit()
        print(f"applied={len(matched)}")
        return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(cleanup_attention_backlog(execute=args.execute))


if __name__ == "__main__":
    raise SystemExit(main())
