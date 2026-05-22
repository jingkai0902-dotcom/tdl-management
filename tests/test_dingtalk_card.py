from datetime import UTC, datetime
from uuid import uuid4

from app.integrations.dingtalk_card import (
    DRAFT_FOLLOW_UP_GUIDE,
    button_status,
    build_card_action_id,
    build_created_card,
    build_draft_card,
    build_reminder_card,
    parse_card_action_id,
    render_interactive_card_data,
    render_markdown,
    render_standard_card_data,
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
    assert "负责人：user-1" in card.body
    assert "完成标准：提交最终方案" in card.body
    assert card.body[-1] == DRAFT_FOLLOW_UP_GUIDE


def test_draft_card_renders_known_owner_name() -> None:
    tdl = StubTDL("draft")
    tdl.owner_id = "0617564550-1513038363"

    card = build_draft_card(tdl)

    assert "负责人：荆少巍 / Frank" in card.body
    assert DRAFT_FOLLOW_UP_GUIDE in card.body


def test_created_card_renders_markdown() -> None:
    card = build_created_card(StubTDL("active"))

    assert "已创建 TDL" in render_markdown(card)
    assert [button.action for button in card.buttons] == ["complete", "snooze", "reject"]


def test_render_markdown_can_hide_non_clickable_actions() -> None:
    card = build_created_card(StubTDL("active"))

    result = render_markdown(card, include_actions=False)

    assert "操作：" not in result
    assert "标记完成" not in result


def test_card_formats_aware_due_at_in_shanghai_time() -> None:
    card = build_created_card(
        StubTDL("active", due_at=datetime(2026, 5, 15, 16, 0, tzinfo=UTC))
    )

    assert "截止：2026-05-16 00:00" in card.body


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
    assert "今天到期，辛苦了" in card.body
    assert "昨天完成了 3 条" in card.body
    assert [button.action for button in card.buttons] == ["complete", "snooze", "reject"]


def test_day_one_reminder_card_uses_soft_reminder_copy() -> None:
    card = build_reminder_card(StubTDL("active"), action="remind_owner", overdue_days=1)

    assert card.title == "有条任务逾期了"
    assert "可能需要看一下" in card.body


def test_day_two_reminder_card_asks_for_support() -> None:
    card = build_reminder_card(StubTDL("active"), action="ask_owner", overdue_days=2)

    assert card.title == "需要支持"
    assert "审核课程方案 已逾期 2 天" in card.body
    assert "是不是卡在什么地方了？" in card.body
    assert [button.action for button in card.buttons] == [
        "complete",
        "postpone",
        "need_help",
        "reject",
    ]


def test_render_interactive_card_data_keeps_button_actions() -> None:
    card = build_reminder_card(StubTDL("active"), action="ask_owner", overdue_days=2)

    result = render_interactive_card_data(card)

    assert result["msgTitle"] == "需要支持"
    assert "审核课程方案 已逾期 2 天" in result["staticMsgContent"]
    assert result["button1Text"] == "已完成"
    assert result["button1ActionId"] == build_card_action_id("complete", card.buttons[0].tdl_id)
    assert result["button1Visible"] == "true"
    assert result["button4Text"] == "不是我的任务"
    assert result["button4ActionId"] == build_card_action_id("reject", card.buttons[3].tdl_id)
    assert result["button4Visible"] == "true"
    assert result["button1Status"] == "primary"
    assert result["button2Status"] == "normal"
    assert result["button3Status"] == "normal"
    assert result["button4Status"] == "normal"


def test_render_interactive_card_data_includes_draft_follow_up_guide() -> None:
    card = build_draft_card(StubTDL("draft"))

    result = render_interactive_card_data(card)

    assert DRAFT_FOLLOW_UP_GUIDE in result["staticMsgContent"]


def test_render_interactive_card_data_hides_unused_button_slots() -> None:
    card = build_reminder_card(StubTDL("active"), action="due_today", overdue_days=0)

    result = render_interactive_card_data(card)

    assert result["button1Text"] == "标记完成"
    assert result["button2Text"] == "暂缓"
    assert result["button3Text"] == "不是我的任务"
    assert result["button4Text"] == ""
    assert result["button4ActionId"] == ""
    assert result["button4Visible"] == "false"
    assert result["button4Status"] == "normal"


def test_button_status_marks_only_primary_actions_primary() -> None:
    card = build_draft_card(StubTDL("draft"))
    cancel_button = card.buttons[-1]

    assert button_status(card.buttons[0]) == "primary"
    assert cancel_button.action == "cancel"
    assert button_status(cancel_button) == "normal"


def test_render_standard_card_data_keeps_button_actions() -> None:
    card = build_reminder_card(StubTDL("active"), action="ask_owner", overdue_days=2)

    result = render_standard_card_data(card)

    assert result["header"]["title"]["text"] == "需要支持"
    assert "审核课程方案 已逾期 2 天" in result["contents"][0]["text"]
    assert (
        result["contents"][2]["actions"][0]["id"]
        == build_card_action_id("complete", card.buttons[0].tdl_id)
    )
    assert result["contents"][2]["actions"][0]["status"] == "primary"
    assert result["contents"][2]["actions"][1]["status"] == "normal"
    assert result["contents"][2]["actions"][2]["status"] == "normal"
    assert result["contents"][2]["actions"][3]["status"] == "normal"


def test_render_standard_card_data_can_hide_button_actions() -> None:
    card = build_reminder_card(StubTDL("active"), action="ask_owner", overdue_days=2)

    result = render_standard_card_data(
        card,
        include_actions=False,
        extra_body_lines=["请直接回复处理。"],
    )

    assert len(result["contents"]) == 1
    assert result["contents"][0]["text"].endswith("请直接回复处理。")


def test_parse_card_action_id_reads_action_and_tdl_id() -> None:
    tdl_id = uuid4()

    assert parse_card_action_id(build_card_action_id("complete", tdl_id)) == (
        "complete",
        tdl_id,
    )
    assert parse_card_action_id("bad-format") is None
