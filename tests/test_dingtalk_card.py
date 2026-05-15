from datetime import UTC, datetime
from uuid import uuid4

from app.integrations.dingtalk_card import build_created_card, build_draft_card, render_markdown


class StubTDL:
    def __init__(self, status: str) -> None:
        self.tdl_id = uuid4()
        self.title = "审核课程方案"
        self.owner_id = "user-1"
        self.due_at = datetime(2026, 5, 20, 18, 0, tzinfo=UTC)
        self.priority = "P1"
        self.status = status


def test_draft_card_contains_confirm_action() -> None:
    card = build_draft_card(StubTDL("draft"))

    assert card.status == "draft"
    assert [button.action for button in card.buttons] == ["confirm", "cancel"]


def test_created_card_renders_markdown() -> None:
    card = build_created_card(StubTDL("active"))

    assert "已创建 TDL" in render_markdown(card)
