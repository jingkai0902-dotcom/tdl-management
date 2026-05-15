from datetime import UTC, datetime
from uuid import uuid4

from app.integrations.dingtalk_card import build_created_card, build_draft_card, render_markdown


_DEFAULT_DUE_AT = object()


class StubTDL:
    def __init__(self, status: str, due_at=_DEFAULT_DUE_AT) -> None:
        self.tdl_id = uuid4()
        self.title = "审核课程方案"
        self.owner_id = "user-1"
        self.due_at = (
            datetime(2026, 5, 20, 18, 0, tzinfo=UTC)
            if due_at is _DEFAULT_DUE_AT
            else due_at
        )
        self.priority = "P1"
        self.status = status


def test_draft_card_contains_confirm_action() -> None:
    card = build_draft_card(StubTDL("draft"))

    assert card.status == "draft"
    assert [button.action for button in card.buttons] == ["confirm", "cancel"]


def test_created_card_renders_markdown() -> None:
    card = build_created_card(StubTDL("active"))

    assert "已创建 TDL" in render_markdown(card)


def test_draft_card_marks_missing_due_at() -> None:
    card = build_draft_card(StubTDL("draft", due_at=None))

    assert "截止：[待补充]" in card.body
