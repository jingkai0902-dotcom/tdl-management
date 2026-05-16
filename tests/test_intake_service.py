from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.integrations.ai_client import TDLExtractionError, TDLFieldDraft, TDLFollowUpDraft
from app.models import TDL
from app.schemas import DingTalkIncomingMessage
from app.services.intake_service import intake_dingtalk_message


class FakeSession:
    def __init__(self) -> None:
        self.items = []

    def add(self, item) -> None:
        self.items.append(item)

    async def flush(self) -> None:
        for item in self.items:
            for attr in ("tdl_id", "audit_id"):
                if hasattr(item, attr) and getattr(item, attr) is None:
                    setattr(item, attr, uuid4())

    async def commit(self) -> None:
        return None

    async def refresh(self, item) -> None:
        return None

    async def execute(self, statement):
        class EmptyResult:
            @staticmethod
            def scalar_one_or_none():
                return None

        return EmptyResult()


class FakeAIClient:
    def __init__(self, draft: TDLFieldDraft) -> None:
        self.draft = draft

    async def extract_tdl_fields(self, source_text: str) -> TDLFieldDraft:
        return self.draft

    async def extract_tdl_follow_up(
        self,
        *,
        draft_title: str,
        source_text: str,
    ) -> TDLFollowUpDraft:
        return TDLFollowUpDraft(
            is_follow_up=False,
            due_at=None,
            completion_criteria=None,
            confidence=0.0,
        )


class FailingAIClient:
    async def extract_tdl_fields(self, source_text: str) -> TDLFieldDraft:
        raise TDLExtractionError("provider unavailable")

    async def extract_tdl_follow_up(
        self,
        *,
        draft_title: str,
        source_text: str,
    ) -> TDLFollowUpDraft:
        raise TDLExtractionError("provider unavailable")


def _message() -> DingTalkIncomingMessage:
    return DingTalkIncomingMessage(
        message_id="msg-1",
        sender_id="0617564550-1513038363",
        sender_nick="Frank",
        content="下周三前审核暑期班方案",
    )


@pytest.mark.asyncio
async def test_intake_auto_creates_low_risk_personal_tdl() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        _message(),
        FakeAIClient(
            TDLFieldDraft(
                title="审核暑期班方案",
                owner_id=None,
                due_at=datetime(2026, 5, 20, 18, 0, tzinfo=UTC),
                completion_criteria="形成最终审核意见",
                priority="P1",
                confidence=0.91,
            )
        ),
    )

    assert card.title == "已创建 TDL"
    assert card.status == "active"


@pytest.mark.asyncio
async def test_intake_keeps_cross_person_task_as_draft() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        _message(),
        FakeAIClient(
            TDLFieldDraft(
                title="时颖提交暑期班方案",
                owner_id="0962151633-1819579479",
                due_at=datetime(2026, 5, 20, 18, 0, tzinfo=UTC),
                completion_criteria=None,
                priority="P1",
                confidence=0.95,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert card.status == "draft"


@pytest.mark.asyncio
async def test_intake_keeps_missing_due_date_as_draft() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        _message(),
        FakeAIClient(
            TDLFieldDraft(
                title="审核暑期班方案",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.95,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert card.status == "draft"


@pytest.mark.asyncio
async def test_intake_falls_back_to_raw_draft_when_ai_fails() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(session, _message(), FailingAIClient())

    assert card.title == "TDL 草稿"
    assert "下周三前审核暑期班方案" in card.body[0]


@pytest.mark.asyncio
async def test_intake_updates_latest_draft_from_text_follow_up(monkeypatch) -> None:
    session = FakeSession()
    draft = TDL(
        tdl_id=uuid4(),
        title="下午去钻石校区教 Claude",
        owner_id="0617564550-1513038363",
        due_at=None,
        completion_criteria=None,
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_incomplete_draft(*args, **kwargs):
        return draft

    async def fake_update_draft_tdl(session, tdl_id, payload, actor_id):
        draft.due_at = payload.due_at
        draft.completion_criteria = payload.completion_criteria
        return draft

    class FollowUpAIClient(FakeAIClient):
        async def extract_tdl_follow_up(
            self,
            *,
            draft_title: str,
            source_text: str,
        ) -> TDLFollowUpDraft:
            return TDLFollowUpDraft(
                is_follow_up=True,
                due_at=datetime(2026, 5, 16, 16, 0, tzinfo=UTC),
                completion_criteria="举几个简单例子并教会基础操作",
                confidence=0.95,
            )

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_incomplete_draft",
        fake_find_latest_incomplete_draft,
    )
    monkeypatch.setattr(
        "app.services.intake_service.update_draft_tdl",
        fake_update_draft_tdl,
    )

    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-2",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="16 点之前完成，完成标准是教会基础操作",
        ),
        FollowUpAIClient(
            TDLFieldDraft(
                title="新任务不该被创建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "2026-05-16 16:00" in card.body[2]
    assert "举几个简单例子并教会基础操作" in card.body[4]
