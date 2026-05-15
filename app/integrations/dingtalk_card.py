from dataclasses import dataclass
from datetime import datetime
import json
from uuid import UUID

from app.models import TDL


@dataclass(frozen=True)
class CardButton:
    label: str
    action: str
    tdl_id: UUID


@dataclass(frozen=True)
class TDLCard:
    title: str
    body: list[str]
    buttons: list[CardButton]
    status: str


def _format_due_at(value: datetime | None) -> str:
    if value is None:
        return "[待补充]"
    return value.strftime("%Y-%m-%d %H:%M")


def build_draft_card(tdl: TDL) -> TDLCard:
    missing_fields = [
        field_name
        for field_name in ("owner_id", "due_at")
        if getattr(tdl, field_name) is None
    ]
    buttons = []
    if "owner_id" in missing_fields:
        buttons.append(CardButton(label="补负责人", action="set_owner", tdl_id=tdl.tdl_id))
    if "due_at" in missing_fields:
        buttons.append(CardButton(label="补截止时间", action="set_due_at", tdl_id=tdl.tdl_id))
    if not missing_fields:
        buttons.append(CardButton(label="确认创建", action="confirm", tdl_id=tdl.tdl_id))
    if tdl.completion_criteria is None:
        buttons.append(
            CardButton(label="补完成标准", action="set_completion_criteria", tdl_id=tdl.tdl_id)
        )
    buttons.append(CardButton(label="忽略", action="cancel", tdl_id=tdl.tdl_id))

    return TDLCard(
        title="TDL 草稿",
        body=[
            tdl.title,
            f"负责人：{tdl.owner_id or '[待补充]'}",
            f"截止：{_format_due_at(tdl.due_at)}",
            f"优先级：{tdl.priority}",
            f"完成标准：{tdl.completion_criteria or '[待补充]'}",
        ],
        buttons=buttons,
        status="draft",
    )


def build_created_card(tdl: TDL) -> TDLCard:
    return TDLCard(
        title="已创建 TDL",
        body=[
            tdl.title,
            f"截止：{_format_due_at(tdl.due_at)}",
            f"优先级：{tdl.priority}",
        ],
        buttons=[
            CardButton(label="标记完成", action="complete", tdl_id=tdl.tdl_id),
            CardButton(label="暂缓", action="snooze", tdl_id=tdl.tdl_id),
        ],
        status=tdl.status,
    )


def build_reminder_card(
    tdl: TDL,
    *,
    action: str,
    overdue_days: int,
    yesterday_completed_count: int | None = None,
) -> TDLCard:
    completion_line = (
        [f"昨天完成了 {yesterday_completed_count} 条"]
        if yesterday_completed_count is not None
        else []
    )
    if action == "due_today":
        return TDLCard(
            title="今日待办",
            body=[
                tdl.title,
                f"截止：{_format_due_at(tdl.due_at)}",
                "这条任务今天到期",
                *completion_line,
            ],
            buttons=[
                CardButton(label="标记完成", action="complete", tdl_id=tdl.tdl_id),
                CardButton(label="暂缓", action="snooze", tdl_id=tdl.tdl_id),
            ],
            status=tdl.status,
        )
    if action == "remind_owner":
        return TDLCard(
            title="任务提醒",
            body=[
                f"{tdl.title} 已逾期 {overdue_days} 天",
                "这条任务可能需要关注",
                *completion_line,
            ],
            buttons=[
                CardButton(label="标记完成", action="complete", tdl_id=tdl.tdl_id),
                CardButton(label="暂缓", action="snooze", tdl_id=tdl.tdl_id),
            ],
            status=tdl.status,
        )
    if action == "ask_owner":
        return TDLCard(
            title="需要支持",
            body=[
                f"{tdl.title} 已逾期 {overdue_days} 天",
                "需要关注一下吗？",
                *completion_line,
            ],
            buttons=[
                CardButton(label="已完成", action="complete", tdl_id=tdl.tdl_id),
                CardButton(label="延期", action="postpone", tdl_id=tdl.tdl_id),
                CardButton(label="需协助", action="need_help", tdl_id=tdl.tdl_id),
            ],
            status=tdl.status,
        )
    raise ValueError(f"Unsupported reminder action: {action}")


def render_markdown(card: TDLCard) -> str:
    lines = [f"## {card.title}", ""]
    lines.extend(card.body)
    if card.buttons:
        lines.extend(["", "操作："])
        lines.extend(f"- {button.label}" for button in card.buttons)
    return "\n".join(lines)


def render_interactive_card_data(card: TDLCard) -> dict[str, str]:
    return {
        "msgTitle": card.title,
        "staticMsgContent": "\n".join(card.body),
        "sys_full_json_obj": json.dumps(
            {
                "order": ["msgTitle", "staticMsgContent", "msgButtons"],
                "msgButtons": [
                    {
                        "text": button.label,
                        "color": "blue" if index == 0 else "gray",
                        "id": build_card_action_id(button.action, button.tdl_id),
                        "request": True,
                    }
                    for index, button in enumerate(card.buttons)
                ],
            },
            ensure_ascii=False,
        ),
    }


def build_card_action_id(action: str, tdl_id: UUID) -> str:
    return f"tdl::{action}::{tdl_id}"
