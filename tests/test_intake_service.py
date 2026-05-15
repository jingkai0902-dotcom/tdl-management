from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.integrations.ai_client import TDLExtractionError, TDLFieldDraft
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


class FakeAIClient:
    def __init__(self, draft: TDLFieldDraft) -> None:
        self.draft = draft

    async def extract_tdl_fields(self, source_text: str) -> TDLFieldDraft:
        return self.draft


class FailingAIClient:
    async def extract_tdl_fields(self, source_text: str) -> TDLFieldDraft:
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
