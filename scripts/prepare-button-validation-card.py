#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import sys
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.integrations.dingtalk_card import build_created_card, build_draft_card, render_interactive_card_data  # noqa: E402
from app.integrations.dingtalk_client import DingTalkClient  # noqa: E402
from app.models import AuditLog, TDL  # noqa: E402

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_TEST_USER_ID = "0617564550-1513038363"
VALIDATION_SOURCE = "button_validation"
VALIDATION_AUDIT_ACTION = "button_validation_create"
CLEANUP_AUDIT_ACTION = "button_validation_cleanup"


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    status: str
    owner_id: str | None
    due_at: datetime | None
    completion_criteria: str | None
    card_kind: str
    instruction: str


def _tomorrow_at(hour: int) -> datetime:
    now = datetime.now(tz=SHANGHAI_TZ)
    return (now + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)


def scenario_for(key: str, *, actor_id: str) -> Scenario:
    due = _tomorrow_at(18)
    scenarios = {
        "d4-owner": Scenario(
            key=key,
            title="Codex按钮验证-D4-补负责人",
            status="draft",
            owner_id=None,
            due_at=due,
            completion_criteria="完成按钮验证记录",
            card_kind="draft",
            instruction="点击“补负责人”，然后在私聊回复：负责人改成李珍",
        ),
        "d5-due": Scenario(
            key=key,
            title="Codex按钮验证-D5-补截止时间",
            status="draft",
            owner_id=actor_id,
            due_at=None,
            completion_criteria="完成按钮验证记录",
            card_kind="draft",
            instruction="点击“补截止时间”，然后在私聊回复：改到明天下午六点",
        ),
        "d6-criteria": Scenario(
            key=key,
            title="Codex按钮验证-D6-补完成标准",
            status="draft",
            owner_id=actor_id,
            due_at=due,
            completion_criteria=None,
            card_kind="draft",
            instruction="点击“补完成标准”，然后在私聊回复：完成标准是列出三条动作",
        ),
        "a4-non-owner": Scenario(
            key=key,
            title="Codex按钮验证-A4-非owner拒绝",
            status="active",
            owner_id="0611436746849471",
            due_at=due,
            completion_criteria="Frank 点击后应被拒绝操作",
            card_kind="created",
            instruction="点击“标记完成”，预期收到“不是分配给你的，不能直接操作”。",
        ),
        "a5-complete": Scenario(
            key=key,
            title="Codex按钮验证-A5-重复完成",
            status="active",
            owner_id=actor_id,
            due_at=due,
            completion_criteria="第一次点击完成，第二次点击同一张旧卡仍返回已处理",
            card_kind="created",
            instruction="连续点击同一张卡片里的“标记完成”两次。",
        ),
    }
    try:
        return scenarios[key]
    except KeyError as exc:
        raise SystemExit(f"Unsupported scenario: {key}") from exc


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare one low-pollution DingTalk button validation card.",
    )
    parser.add_argument(
        "--scenario",
        choices=("d4-owner", "d5-due", "d6-criteria", "a4-non-owner", "a5-complete"),
        help="Scenario to prepare.",
    )
    parser.add_argument(
        "--user-id",
        default=DEFAULT_TEST_USER_ID,
        help="DingTalk user ID that receives the validation card. Defaults to Frank.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run id for grouping validation records. Defaults to a generated id.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Create the validation TDL and send the DingTalk card. Without this, only preview.",
    )
    parser.add_argument(
        "--cleanup-run-id",
        help="Cancel validation TDLs created for this run id.",
    )
    parser.add_argument(
        "--execute-cleanup",
        action="store_true",
        help="Apply cleanup for --cleanup-run-id. Without this, only dry-run.",
    )
    return parser.parse_args(argv)


async def _create_validation_tdl(
    scenario: Scenario,
    *,
    actor_id: str,
    run_id: str,
) -> TDL:
    async with SessionLocal() as session:
        tdl = TDL(
            title=scenario.title,
            owner_id=scenario.owner_id,
            due_at=scenario.due_at,
            status=scenario.status,
            priority="P2",
            source=VALIDATION_SOURCE,
            created_by=actor_id,
            completion_criteria=scenario.completion_criteria,
        )
        session.add(tdl)
        await session.flush()
        session.add(
            AuditLog(
                entity_type="tdl",
                entity_id=str(tdl.tdl_id),
                action=VALIDATION_AUDIT_ACTION,
                actor_id=actor_id,
                payload={
                    "run_id": run_id,
                    "scenario": scenario.key,
                    "source": VALIDATION_SOURCE,
                },
            )
        )
        await session.commit()
        await session.refresh(tdl)
        return tdl


async def _send_card(tdl: TDL, *, card_kind: str, user_id: str) -> None:
    settings = get_settings()
    if not settings.dingtalk_tdl_card_template_id:
        raise SystemExit("DINGTALK_TDL_CARD_TEMPLATE_ID is not configured")
    card = build_draft_card(tdl) if card_kind == "draft" else build_created_card(tdl)
    client = DingTalkClient()
    try:
        await client.send_interactive_card_to_user(
            user_id=user_id,
            card_template_id=settings.dingtalk_tdl_card_template_id,
            card_data=render_interactive_card_data(card),
        )
    finally:
        await client.close()


async def _cleanup_run(run_id: str, *, execute: bool) -> int:
    async with SessionLocal() as session:
        audit_result = await session.execute(
            select(AuditLog).where(
                AuditLog.action == VALIDATION_AUDIT_ACTION,
                AuditLog.payload["run_id"].as_string() == run_id,
            )
        )
        audits = list(audit_result.scalars().all())
        tdl_ids = [audit.entity_id for audit in audits]
        tdl_result = await session.execute(select(TDL).where(TDL.tdl_id.in_(tdl_ids)))
        tdls = list(tdl_result.scalars().all())
        print(f"dry_run={not execute}")
        print(f"run_id={run_id}")
        print(f"matched={len(tdls)}")
        for tdl in tdls:
            print(f"candidate | {tdl.tdl_id} | {tdl.status} -> canceled | {tdl.title}")
        if not execute:
            return 0
        for tdl in tdls:
            previous_status = tdl.status
            tdl.status = "canceled"
            tdl.cancel_reason = "button_validation_cleanup"
            session.add(
                AuditLog(
                    entity_type="tdl",
                    entity_id=str(tdl.tdl_id),
                    action=CLEANUP_AUDIT_ACTION,
                    actor_id="codex",
                    payload={"run_id": run_id, "previous_status": previous_status},
                )
            )
        await session.commit()
        print(f"applied={len(tdls)}")
        return 0


async def main() -> int:
    args = _parse_args()
    if args.cleanup_run_id:
        return await _cleanup_run(args.cleanup_run_id, execute=args.execute_cleanup)
    if not args.scenario:
        raise SystemExit("--scenario is required unless --cleanup-run-id is provided")
    run_id = args.run_id or f"button-validation-{datetime.now(tz=SHANGHAI_TZ):%Y%m%d%H%M%S}"
    scenario = scenario_for(args.scenario, actor_id=args.user_id)
    print(f"dry_run={not args.send}")
    print(f"run_id={run_id}")
    print(f"scenario={scenario.key}")
    print(f"title={scenario.title}")
    print(f"instruction={scenario.instruction}")
    if not args.send:
        return 0
    tdl = await _create_validation_tdl(scenario, actor_id=args.user_id, run_id=run_id)
    await _send_card(tdl, card_kind=scenario.card_kind, user_id=args.user_id)
    print(f"created_tdl_id={tdl.tdl_id}")
    print("card_sent=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
