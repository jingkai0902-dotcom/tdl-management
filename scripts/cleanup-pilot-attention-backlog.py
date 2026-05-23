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
CLEANUP_AUDIT_ACTION = "pilot_cleanup_cancel"


@dataclass(frozen=True)
class CleanupCandidate:
    tdl_id: str
    title: str
    reason: str
    classification: str
    expected_status: str = "attention"


TEST_RESIDUAL_CANDIDATES: tuple[CleanupCandidate, ...] = (
    CleanupCandidate(
        "bd4434a0-3c9b-4f03-a1c4-0df566b1144a",
        "日历同步联调测试",
        "manual calendar integration test",
        "test_residual",
    ),
    CleanupCandidate(
        "0d8beb4a-8815-4de2-81c4-b0ee696a6ed1",
        "完成日历同步验证",
        "calendar integration verification",
        "test_residual",
    ),
    CleanupCandidate(
        "15ea9f17-740f-4b7a-8b77-a36652bfbdae",
        "测试日历联动",
        "calendar integration test",
        "test_residual",
    ),
    CleanupCandidate(
        "8498bd5f-47e2-4e72-9704-a02b4578d3f5",
        "向李祯提交今日工作总结并请其审阅反馈",
        "old owner typo test sample",
        "test_residual",
    ),
    CleanupCandidate(
        "fea1a5a6-a699-4c0c-bf23-da3f1781a1af",
        "将姓名更正为李珍（珍珠的珍），即 Helen",
        "old correction false-positive sample",
        "test_residual",
    ),
    CleanupCandidate(
        "0fa465cf-8461-4c32-8612-682af2f403e1",
        "【Codex真实按钮测试-暂缓】请点击暂缓",
        "live button test",
        "test_residual",
    ),
    CleanupCandidate(
        "8285fa28-1228-4a23-9995-7112ef8e8e71",
        "完成 Codex 草稿模板卡 D1 复测",
        "Codex draft card test",
        "test_residual",
    ),
    CleanupCandidate(
        "d7812381-6ed3-48e4-81da-6ae24c3b8c83",
        "完成Codex A2暂缓测试",
        "Codex snooze test",
        "test_residual",
    ),
)


STALE_ATTENTION_CANDIDATES: tuple[CleanupCandidate, ...] = (
    CleanupCandidate(
        "a8dc143d-d6ba-4b80-88d2-fd2b2b99daed",
        "前往钻石校区教授Claude使用方法",
        "stale pilot task already overdue before stable calendar sync",
        "stale_attention",
    ),
    CleanupCandidate(
        "6d8678bd-81ee-45bb-85cf-4caba0f93dd6",
        "教会他们基础操作，举3个例子",
        "stale pilot task already overdue before stable calendar sync",
        "stale_attention",
    ),
    CleanupCandidate(
        "0cad58f6-da83-46dc-a070-c5cdfc95634e",
        "整理本周招聘数据，输出 1 页汇总",
        "stale pilot task already overdue before stable calendar sync",
        "stale_attention",
    ),
    CleanupCandidate(
        "5d895a40-9444-4235-8c57-fe8a432f8d26",
        "整理本周招生复盘",
        "stale pilot task already overdue before stable calendar sync",
        "stale_attention",
    ),
    CleanupCandidate(
        "1b6deda7-abfa-45f2-8607-aa1e9d92748c",
        "整理招生复盘",
        "stale pilot task with old invalid auth failure",
        "stale_attention",
    ),
    CleanupCandidate(
        "b76daa5a-1732-4bb3-81c6-d2fbd04e3ec8",
        "核对薪资规则",
        "stale pilot task already marked attention",
        "stale_attention",
    ),
    CleanupCandidate(
        "21116466-c9c9-4b2e-856d-19cf933a9c49",
        "完成薪资规则复核",
        "stale pilot task already marked attention",
        "stale_attention",
    ),
    CleanupCandidate(
        "b3236830-055e-4e2d-a5a2-693498c89cec",
        "核验薪资规则，确认三条异常",
        "stale pilot task already marked attention",
        "stale_attention",
    ),
    CleanupCandidate(
        "710c5f2b-c526-415a-85de-0632f7746ab8",
        "完成招生方案修订",
        "stale pilot task already marked attention",
        "stale_attention",
    ),
    CleanupCandidate(
        "98d55198-58e0-42b2-9d95-937569600800",
        "处理家长投诉",
        "stale pilot task already marked attention",
        "stale_attention",
    ),
)


DRAFT_RESIDUAL_CANDIDATES: tuple[CleanupCandidate, ...] = (
    CleanupCandidate(
        "224f2f35-1061-414d-996b-05b13514331d",
        "完成 Codex 草稿按钮 D1 测试",
        "stale Codex draft button test",
        "draft_residual",
        "draft",
    ),
    CleanupCandidate(
        "47d1e643-8dd6-4c47-9f48-932ee3a50670",
        "补充说明：任务负责人为李珍，非石影",
        "orphan contextual follow-up false positive before no-target guard",
        "draft_false_positive",
        "draft",
    ),
)


def _candidates_for_category(category: str) -> tuple[CleanupCandidate, ...]:
    if category == "test-residual":
        return TEST_RESIDUAL_CANDIDATES
    if category == "stale-attention":
        return STALE_ATTENTION_CANDIDATES
    if category == "draft-residual":
        return DRAFT_RESIDUAL_CANDIDATES
    if category == "all":
        return TEST_RESIDUAL_CANDIDATES + STALE_ATTENTION_CANDIDATES + DRAFT_RESIDUAL_CANDIDATES
    raise ValueError(f"Unsupported cleanup category: {category}")


def _cleanup_reason(category: str) -> str:
    if category == "test-residual":
        return "pilot_test_residual_cleanup"
    if category == "stale-attention":
        return "pilot_stale_backlog_cleanup"
    if category == "draft-residual":
        return "pilot_draft_residual_cleanup"
    return "pilot_backlog_cleanup"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cancel explicit allowlisted pilot backlog items.",
    )
    parser.add_argument(
        "--category",
        choices=("test-residual", "stale-attention", "draft-residual", "all"),
        default="test-residual",
        help="Allowlist category to clean. Defaults to the original test residual set.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply cleanup. Without this flag the script only prints a dry-run report.",
    )
    return parser.parse_args(argv)


async def cleanup_attention_backlog(*, category: str, execute: bool) -> int:
    candidates = _candidates_for_category(category)
    cleanup_reason = _cleanup_reason(category)
    async with SessionLocal() as session:
        result = await session.execute(
            select(TDL).where(
                TDL.tdl_id.in_([UUID(candidate.tdl_id) for candidate in candidates])
            )
        )
        tdls_by_id = {str(tdl.tdl_id): tdl for tdl in result.scalars().all()}

        errors: list[str] = []
        matched: list[tuple[CleanupCandidate, TDL]] = []
        for candidate in candidates:
            tdl = tdls_by_id.get(candidate.tdl_id)
            if tdl is None:
                errors.append(f"missing | {candidate.tdl_id} | {candidate.title}")
                continue
            if tdl.title != candidate.title:
                errors.append(
                    f"title_mismatch | {candidate.tdl_id} | expected={candidate.title} | actual={tdl.title}"
                )
                continue
            if tdl.status != candidate.expected_status:
                errors.append(
                    f"status_mismatch | {candidate.tdl_id} | "
                    f"expected={candidate.expected_status} | actual={tdl.status}"
                )
                continue
            matched.append((candidate, tdl))

        print(f"dry_run={not execute}")
        print(f"category={category}")
        print(f"expected={len(candidates)} matched={len(matched)} errors={len(errors)}")
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
            tdl.cancel_reason = cleanup_reason
            session.add(
                AuditLog(
                    entity_type="tdl",
                    entity_id=str(tdl.tdl_id),
                    action=CLEANUP_AUDIT_ACTION,
                    actor_id=CLEANUP_ACTOR_ID,
                    payload={
                        "reason": cleanup_reason,
                        "previous_status": previous_status,
                        "classification": candidate.classification,
                        "classification_reason": candidate.reason,
                    },
                )
            )
        await session.commit()
        print(f"applied={len(matched)}")
        return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(cleanup_attention_backlog(category=args.category, execute=args.execute))


if __name__ == "__main__":
    raise SystemExit(main())
