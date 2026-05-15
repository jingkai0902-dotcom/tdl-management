from dataclasses import dataclass
from datetime import datetime
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
    return TDLCard(
        title="TDL 草稿",
        body=[
            tdl.title,
            f"负责人：{tdl.owner_id}",
            f"截止：{_format_due_at(tdl.due_at)}",
            f"优先级：{tdl.priority}",
        ],
        buttons=[
            CardButton(label="确认创建", action="confirm", tdl_id=tdl.tdl_id),
            CardButton(label="忽略", action="cancel", tdl_id=tdl.tdl_id),
        ],
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


def render_markdown(card: TDLCard) -> str:
    lines = [f"## {card.title}", ""]
    lines.extend(card.body)
    if card.buttons:
        lines.extend(["", "操作："])
        lines.extend(f"- {button.label}" for button in card.buttons)
    return "\n".join(lines)
