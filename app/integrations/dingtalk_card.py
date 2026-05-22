from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.config import load_yaml_config
from app.models import TDL


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DRAFT_FOLLOW_UP_GUIDE = "可直接回复“改成李珍”“时间改到下周五”“完成标准是形成一页结论”来修正。"
PRIMARY_BUTTON_ACTIONS = {"confirm", "complete"}


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
    if value.tzinfo is not None:
        value = value.astimezone(SHANGHAI_TZ)
    return value.strftime("%Y-%m-%d %H:%M")


def _format_owner(owner_id: str | None) -> str:
    if owner_id is None:
        return "[待补充]"
    roster = load_yaml_config("management_roster.yaml")
    for member in roster.get("management", []):
        if str(member.get("dingtalk_user_id")) != owner_id:
            continue
        name = member.get("name")
        english_name = member.get("english_name")
        if name and english_name:
            return f"{name} / {english_name}"
        if name:
            return str(name)
    return owner_id


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
            f"负责人：{_format_owner(tdl.owner_id)}",
            f"截止：{_format_due_at(tdl.due_at)}",
            f"优先级：{tdl.priority}",
            f"完成标准：{tdl.completion_criteria or '[待补充]'}",
            DRAFT_FOLLOW_UP_GUIDE,
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
            CardButton(label="不是我的任务", action="reject", tdl_id=tdl.tdl_id),
        ],
        status=tdl.status,
    )


def build_canceled_card(tdl: TDL) -> TDLCard:
    return TDLCard(
        title="已忽略草稿",
        body=[
            tdl.title,
        ],
        buttons=[],
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
                "今天到期，辛苦了",
                *completion_line,
            ],
            buttons=[
                CardButton(label="标记完成", action="complete", tdl_id=tdl.tdl_id),
                CardButton(label="暂缓", action="snooze", tdl_id=tdl.tdl_id),
                CardButton(label="不是我的任务", action="reject", tdl_id=tdl.tdl_id),
            ],
            status=tdl.status,
        )
    if action == "remind_owner":
        return TDLCard(
            title="有条任务逾期了",
            body=[
                f"{tdl.title} 已逾期 {overdue_days} 天",
                "可能需要看一下",
                *completion_line,
            ],
            buttons=[
                CardButton(label="标记完成", action="complete", tdl_id=tdl.tdl_id),
                CardButton(label="暂缓", action="snooze", tdl_id=tdl.tdl_id),
                CardButton(label="不是我的任务", action="reject", tdl_id=tdl.tdl_id),
            ],
            status=tdl.status,
        )
    if action == "ask_owner":
        return TDLCard(
            title="需要支持",
            body=[
                f"{tdl.title} 已逾期 {overdue_days} 天",
                "是不是卡在什么地方了？",
                *completion_line,
            ],
            buttons=[
                CardButton(label="已完成", action="complete", tdl_id=tdl.tdl_id),
                CardButton(label="延期", action="postpone", tdl_id=tdl.tdl_id),
                CardButton(label="需协助", action="need_help", tdl_id=tdl.tdl_id),
                CardButton(label="不是我的任务", action="reject", tdl_id=tdl.tdl_id),
            ],
            status=tdl.status,
        )
    raise ValueError(f"Unsupported reminder action: {action}")


def render_markdown(card: TDLCard, *, include_actions: bool = True) -> str:
    lines = [f"## {card.title}", ""]
    lines.extend(card.body)
    if include_actions and card.buttons:
        lines.extend(["", "操作："])
        lines.extend(f"- {button.label}" for button in card.buttons)
    return "\n".join(lines)


def render_interactive_card_data(card: TDLCard) -> dict[str, str]:
    """Render data for a DingTalk builder template with fixed button slots."""
    result = {
        "msgTitle": card.title,
        "staticMsgContent": "\n".join(card.body),
    }
    for index in range(4):
        slot = index + 1
        if index < len(card.buttons):
            button = card.buttons[index]
            result[f"button{slot}Text"] = button.label
            result[f"button{slot}ActionId"] = build_card_action_id(button.action, button.tdl_id)
            result[f"button{slot}Visible"] = "true"
            result[f"button{slot}Status"] = button_status(button)
        else:
            result[f"button{slot}Text"] = ""
            result[f"button{slot}ActionId"] = ""
            result[f"button{slot}Visible"] = "false"
            result[f"button{slot}Status"] = "normal"
    return result


def button_status(button: CardButton) -> str:
    return "primary" if button.action in PRIMARY_BUTTON_ACTIONS else "normal"


def render_standard_card_data(
    card: TDLCard,
    *,
    include_actions: bool = True,
    extra_body_lines: list[str] | None = None,
) -> dict:
    """Render a built-in DingTalk StandardCard payload for chatbot replies."""
    body_lines = [*card.body, *(extra_body_lines or [])]
    contents = [
        {
            "type": "markdown",
            "text": "\n".join(body_lines),
            "id": "tdl_body",
        }
    ]
    if include_actions and card.buttons:
        contents.append({"type": "divider", "id": "tdl_divider"})
        contents.append(
            {
                "type": "action",
                "actions": [
                    {
                        "type": "button",
                        "label": {
                            "type": "text",
                            "text": button.label,
                            "id": f"tdl_button_label_{index}",
                        },
                        "actionType": "request",
                        "status": button_status(button),
                        "id": build_card_action_id(button.action, button.tdl_id),
                    }
                    for index, button in enumerate(card.buttons)
                ],
                "id": "tdl_actions",
            }
        )
    return {
        "config": {"autoLayout": True, "enableForward": False},
        "header": {
            "title": {"type": "text", "text": card.title},
        },
        "contents": contents,
    }


def build_card_action_id(action: str, tdl_id: UUID) -> str:
    return f"tdl::{action}::{tdl_id}"


def parse_card_action_id(action_id: str) -> tuple[str, UUID] | None:
    parts = action_id.split("::")
    if len(parts) != 3 or parts[0] != "tdl":
        return None
    try:
        return parts[1], UUID(parts[2])
    except ValueError:
        return None
