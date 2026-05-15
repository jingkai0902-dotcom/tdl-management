from datetime import UTC, datetime
from uuid import uuid4

from app.integrations.dingtalk_card import (
    build_created_card,
    build_draft_card,
    build_reminder_card,
    render_markdown,
)


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
        self.completion_criteria = "提交最终方案"


def test_draft_card_contains_confirm_action() -> None:
    card = build_draft_card(StubTDL("draft"))

    assert card.status == "draft"
    assert [button.action for button in card.buttons] == ["confirm", "cancel"]
    assert "完成标准：提交最终方案" in card.body


def test_created_card_renders_markdown() -> None:
    card = build_created_card(StubTDL("active"))

    assert "已创建 TDL" in render_markdown(card)


def test_draft_card_marks_missing_due_at() -> None:
    card = build_draft_card(StubTDL("draft", due_at=None))

    assert "截止：[待补充]" in card.body
    assert [button.action for button in card.buttons] == ["set_due_at", "cancel"]


def test_draft_card_marks_missing_owner() -> None:
    tdl = StubTDL("draft")
    tdl.owner_id = None

    card = build_draft_card(tdl)

    assert "负责人：[待补充]" in card.body
    assert [button.action for button in card.buttons] == ["set_owner", "cancel"]


def test_draft_card_marks_all_missing_fields() -> None:
    tdl = StubTDL("draft", due_at=None)
    tdl.owner_id = None

    card = build_draft_card(tdl)

    assert [button.action for button in card.buttons] == ["set_owner", "set_due_at", "cancel"]


def test_draft_card_marks_missing_completion_criteria() -> None:
    tdl = StubTDL("draft")
    tdl.completion_criteria = None

    card = build_draft_card(tdl)

    assert "完成标准：[待补充]" in card.body
    assert [button.action for button in card.buttons] == [
        "confirm",
        "set_completion_criteria",
        "cancel",
    ]


def test_due_today_card_uses_daily_reminder_actions() -> None:
    card = build_reminder_card(
        StubTDL("active"),
        action="due_today",
        overdue_days=0,
        yesterday_completed_count=3,
    )

    assert card.title == "今日待办"
    assert "这条任务今天到期" in card.body
    assert "昨天完成了 3 条" in card.body
    assert [button.action for button in card.buttons] == ["complete", "snooze"]


def test_day_two_reminder_card_asks_for_support() -> None:
    card = build_reminder_card(StubTDL("active"), action="ask_owner", overdue_days=2)

    assert card.title == "需要支持"
    assert "审核课程方案 已逾期 2 天" in card.body
    assert [button.action for button in card.buttons] == ["complete", "postpone", "need_help"]
