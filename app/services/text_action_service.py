from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from zoneinfo import ZoneInfo

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.dingtalk_card import TDLCard
from app.models import TDL
from app.services.tdl_service import complete_tdl, reject_tdl, snooze_tdl


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
ACTIONABLE_STATUSES = {"active", "attention", "snoozed"}


@dataclass(frozen=True)
class TextActionCommand:
    action: str
    query: str | None = None


def parse_text_action_command(source_text: str) -> TextActionCommand | None:
    text = source_text.strip()
    normalized = _normalize_command_text(text)
    if normalized in {"完成", "已完成", "标记完成", "做完了", "搞定"}:
        return TextActionCommand(action="complete")
    if normalized in {"不是我的任务", "不归我", "非我任务"}:
        return TextActionCommand(action="reject")
    if normalized in {"暂缓", "延期", "稍后提醒"}:
        return TextActionCommand(action="snooze")

    parsed = _parse_prefixed_command(text)
    if parsed is not None:
        return parsed
    return None


async def handle_text_action_command(
    session: AsyncSession,
    *,
    actor_id: str,
    source_text: str,
    now: datetime | None = None,
) -> TDLCard | None:
    command = parse_text_action_command(source_text)
    if command is None:
        return None

    candidates = await find_actionable_owned_tdls(session, owner_id=actor_id)
    target = _resolve_target(candidates, command.query)
    if isinstance(target, TDLCard):
        return target

    if command.action == "complete":
        tdl = await complete_tdl(session, target.tdl_id, actor_id)
        return _build_result_card("已标记完成", tdl)
    if command.action == "reject":
        tdl = await reject_tdl(
            session,
            target.tdl_id,
            actor_id,
            reason="owner_rejected_by_text_command",
        )
        return _build_result_card("已标记为不是我的任务", tdl)
    if command.action == "snooze":
        snooze_until = _default_snooze_until(now or datetime.now(tz=SHANGHAI_TZ))
        tdl = await snooze_tdl(
            session,
            target.tdl_id,
            snooze_until=snooze_until,
            actor_id=actor_id,
        )
        return _build_result_card(
            "已暂缓",
            tdl,
            extra_lines=[f"下次提醒：{snooze_until.astimezone(SHANGHAI_TZ):%Y-%m-%d %H:%M}"],
        )
    return None


async def find_actionable_owned_tdls(session: AsyncSession, *, owner_id: str) -> list[TDL]:
    status_rank = case(
        (TDL.status == "attention", 0),
        (TDL.status == "active", 1),
        (TDL.status == "snoozed", 2),
        else_=3,
    )
    result = await session.execute(
        select(TDL)
        .where(TDL.owner_id == owner_id, TDL.status.in_(ACTIONABLE_STATUSES))
        .order_by(status_rank, TDL.due_at.asc().nulls_last(), TDL.updated_at.desc())
        .limit(10)
    )
    return list(result.scalars().all())


def _parse_prefixed_command(text: str) -> TextActionCommand | None:
    match = re.match(
        r"^(完成|已完成|标记完成|做完了|搞定|不是我的任务|不归我|非我任务|暂缓|延期|稍后提醒)\s*[:：,，]?\s*(.+)$",
        text,
    )
    if not match:
        return None
    verb, query = match.groups()
    action = {
        "完成": "complete",
        "已完成": "complete",
        "标记完成": "complete",
        "做完了": "complete",
        "搞定": "complete",
        "不是我的任务": "reject",
        "不归我": "reject",
        "非我任务": "reject",
        "暂缓": "snooze",
        "延期": "snooze",
        "稍后提醒": "snooze",
    }[verb]
    query = _strip_snooze_time_words(query) if action == "snooze" else query
    return TextActionCommand(action=action, query=query.strip() or None)


def _resolve_target(candidates: list[TDL], query: str | None) -> TDL | TDLCard:
    if not candidates:
        return _build_message_card(
            "没有找到可处理任务",
            ["当前没有分配给你的进行中、需关注或暂缓任务。"],
        )
    if query is None:
        if len(candidates) == 1:
            return candidates[0]
        return _build_ambiguous_card(candidates)

    query_normalized = _normalize_match_text(query)
    matches = [
        tdl
        for tdl in candidates
        if query_normalized in _normalize_match_text(tdl.title)
        or _normalize_match_text(tdl.title) in query_normalized
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return _build_ambiguous_card(matches)
    return _build_message_card(
        "没匹配到任务",
        [
            f"没有找到标题包含“{query.strip()}”的可处理任务。",
            "可以回复“完成：任务标题”“暂缓：任务标题”或“不是我的任务：任务标题”。",
        ],
    )


def _build_ambiguous_card(candidates: list[TDL]) -> TDLCard:
    lines = ["你有多条可处理任务，请带上任务标题再操作。"]
    lines.extend(f"- {tdl.title}" for tdl in candidates[:5])
    lines.append("例如：完成：任务标题")
    return _build_message_card("需要指定任务", lines)


def _build_result_card(title: str, tdl: TDL, *, extra_lines: list[str] | None = None) -> TDLCard:
    return TDLCard(
        title=title,
        body=[tdl.title, *(extra_lines or [])],
        buttons=[],
        status=tdl.status,
    )


def _build_message_card(title: str, body: list[str]) -> TDLCard:
    return TDLCard(title=title, body=body, buttons=[], status="info")


def _default_snooze_until(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    local_now = now.astimezone(SHANGHAI_TZ)
    tomorrow = local_now + timedelta(days=1)
    return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)


def _normalize_command_text(text: str) -> str:
    return re.sub(r"[\s。！？!?.，,：:]", "", text)


def _normalize_match_text(text: str) -> str:
    return re.sub(r"[\s。！？!?.，,：:、（）()《》\"']", "", text).lower()


def _strip_snooze_time_words(query: str) -> str:
    return re.sub(r"^(到)?(明天|今天|后天)?\s*\d{0,2}\s*(点|时)?\s*[:：,，]?", "", query).strip()
