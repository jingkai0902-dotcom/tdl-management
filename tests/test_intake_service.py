from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.integrations.ai_client import TDLExtractionError, TDLFieldDraft, TDLFollowUpDraft
from app.models import TDL
from app.schemas import DingTalkIncomingMessage
from app.services.intake_service import intake_dingtalk_message


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


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

    async def get(self, model, identifier):
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
async def test_intake_blocks_auto_create_when_message_mentions_other_manager() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-other-manager",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="让时颖下周一 18 点前提交活动复盘",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="提交活动复盘",
                owner_id=None,
                due_at=datetime(2026, 5, 18, 18, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria="交一页结论",
                priority="P1",
                confidence=0.95,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert card.status == "draft"
    assert "负责人：时颖 / Sherry" in card.body


@pytest.mark.asyncio
async def test_intake_defaults_to_sender_when_other_manager_is_only_collaborator() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-collaborator",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="下周一和李珍聊一下招生复盘",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="与李珍沟通招生复盘",
                owner_id=None,
                due_at=datetime(2026, 5, 18, 0, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria=None,
                priority="P2",
                confidence=0.95,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert card.status == "draft"
    assert "负责人：荆少巍 / Frank" in card.body
    assert "截止：2026-05-18 18:00" in card.body


@pytest.mark.asyncio
async def test_intake_normalizes_date_only_due_at_to_end_of_workday() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-date-only",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="请时颖下周三前提交直播复盘，完成标准是形成一页结论",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="提交直播复盘",
                owner_id="0962151633-1819579479",
                due_at=datetime(2026, 5, 20, 0, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria="形成一页结论",
                priority="P1",
                confidence=0.95,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "截止：2026-05-20 18:00" in card.body


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
async def test_intake_drops_due_at_inferred_from_ambiguous_time_text() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-ambiguous",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="下午要去钻石校区，教他们用 Claude",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="前往钻石校区教授 Claude 使用方法",
                owner_id=None,
                due_at=datetime(2026, 5, 16, 0, 0, tzinfo=UTC),
                completion_criteria=None,
                priority="P2",
                confidence=0.95,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "截止：[待补充]" in card.body
    assert "优先级：P2" in card.body


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
                    due_at=datetime(2026, 5, 16, 16, 0, tzinfo=SHANGHAI_TZ),
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


@pytest.mark.asyncio
async def test_intake_skips_follow_up_ai_for_obvious_new_cross_person_task(monkeypatch) -> None:
    session = FakeSession()
    draft = TDL(
        tdl_id=uuid4(),
        title="与李珍沟通招生复盘",
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 18, 18, 0, tzinfo=SHANGHAI_TZ),
        completion_criteria=None,
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_incomplete_draft(*args, **kwargs):
        return draft

    class CountingAIClient(FakeAIClient):
        def __init__(self, tdl_draft: TDLFieldDraft) -> None:
            super().__init__(tdl_draft)
            self.follow_up_calls = 0

        async def extract_tdl_follow_up(
            self,
            *,
            draft_title: str,
            source_text: str,
        ) -> TDLFollowUpDraft:
            self.follow_up_calls += 1
            return await super().extract_tdl_follow_up(
                draft_title=draft_title,
                source_text=source_text,
            )

    client = CountingAIClient(
        TDLFieldDraft(
            title="提交直播复盘",
            owner_id="0962151633-1819579479",
            due_at=datetime(2026, 5, 20, 18, 0, tzinfo=SHANGHAI_TZ),
            completion_criteria="形成一页结论",
            priority="P1",
            confidence=0.95,
        )
    )

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_incomplete_draft",
        fake_find_latest_incomplete_draft,
    )

    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-new-task-after-draft",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="请时颖下周三前提交直播复盘，完成标准是形成一页结论",
        ),
        client,
    )

    assert client.follow_up_calls == 0
    assert card.title == "TDL 草稿"
    assert "负责人：时颖 / Sherry" in card.body


@pytest.mark.asyncio
async def test_intake_updates_owner_from_correction_even_when_message_mentions_manager(monkeypatch) -> None:
    session = FakeSession()
    draft = TDL(
        tdl_id=uuid4(),
        title="提交复盘方案",
        owner_id=None,
        due_at=datetime(2026, 5, 20, 18, 0, tzinfo=SHANGHAI_TZ),
        completion_criteria=None,
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_incomplete_draft(*args, **kwargs):
        return draft

    async def fake_update_draft_tdl(session, tdl_id, payload, actor_id):
        draft.owner_id = payload.owner_id
        draft.due_at = payload.due_at or draft.due_at
        draft.completion_criteria = payload.completion_criteria
        return draft

    class CorrectionAIClient(FakeAIClient):
        async def extract_tdl_follow_up(
            self,
            *,
            draft_title: str,
            source_text: str,
        ) -> TDLFollowUpDraft:
            return TDLFollowUpDraft(
                is_follow_up=True,
                due_at=None,
                completion_criteria=None,
                confidence=0.93,
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
            message_id="msg-correct-owner",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="刚才打错字了，是李祯，珍珠的珍",
        ),
        CorrectionAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "负责人：李珍 / Helen" in card.body


@pytest.mark.asyncio
async def test_intake_updates_owner_from_not_old_name_but_new_name_correction(monkeypatch) -> None:
    session = FakeSession()
    draft = TDL(
        tdl_id=uuid4(),
        title="提交复盘方案",
        owner_id="0962151633-1819579479",
        due_at=datetime(2026, 5, 20, 18, 0, tzinfo=SHANGHAI_TZ),
        completion_criteria=None,
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_incomplete_draft(*args, **kwargs):
        return draft

    async def fake_update_draft_tdl(session, tdl_id, payload, actor_id):
        draft.owner_id = payload.owner_id
        return draft

    class LowConfidenceAIClient(FakeAIClient):
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
                confidence=0.20,
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
            message_id="msg-correct-owner-from-old-to-new",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="刚才那条负责人不是时颖，是李珍",
        ),
        LowConfidenceAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "负责人：李珍 / Helen" in card.body


@pytest.mark.asyncio
async def test_intake_updates_recent_active_tdl_from_explicit_owner_correction(monkeypatch) -> None:
    session = FakeSession()
    active_tdl = TDL(
        tdl_id=uuid4(),
        title="组织斯坦教学员工集体磨课",
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 21, 16, 0, tzinfo=SHANGHAI_TZ),
        completion_criteria="每一位斯坦教学员工都完成了一次磨课",
        priority="P1",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="active",
    )

    async def fake_find_latest_incomplete_draft(*args, **kwargs):
        return None

    async def fake_find_latest_recent_open_tdl(*args, **kwargs):
        return active_tdl

    async def fake_update_open_tdl_from_follow_up(session, tdl_id, payload, actor_id):
        active_tdl.owner_id = payload.owner_id
        active_tdl.due_at = payload.due_at or active_tdl.due_at
        active_tdl.completion_criteria = payload.completion_criteria or active_tdl.completion_criteria
        return active_tdl

    async def fake_sync_calendar_due_at_change_best_effort(session, tdl, *, actor_id, client=None):
        return tdl

    class LowConfidenceAIClient(FakeAIClient):
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
                confidence=0.20,
            )

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_incomplete_draft",
        fake_find_latest_incomplete_draft,
    )
    monkeypatch.setattr(
        "app.services.intake_service.find_latest_recent_open_tdl",
        fake_find_latest_recent_open_tdl,
    )
    monkeypatch.setattr(
        "app.services.intake_service.update_open_tdl_from_follow_up",
        fake_update_open_tdl_from_follow_up,
    )
    monkeypatch.setattr(
        "app.services.intake_service.sync_calendar_due_at_change_best_effort",
        fake_sync_calendar_due_at_change_best_effort,
    )

    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-correct-active-owner",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="嗯，需要补充一下刚才发的这一条。不是石影的，是李珍的任务。不是siri",
        ),
        LowConfidenceAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "已创建 TDL"
    assert active_tdl.status == "active"
    assert active_tdl.owner_id == "0611436746849471"


@pytest.mark.asyncio
async def test_intake_updates_recent_active_tdl_from_due_at_and_criteria_correction(monkeypatch) -> None:
    session = FakeSession()
    active_tdl = TDL(
        tdl_id=uuid4(),
        title="组织斯坦教学员工集体磨课",
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 21, 16, 0, tzinfo=SHANGHAI_TZ),
        completion_criteria="每一位斯坦教学员工都完成了一次磨课",
        priority="P1",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="active",
    )

    async def fake_find_latest_incomplete_draft(*args, **kwargs):
        return None

    async def fake_find_latest_recent_open_tdl(*args, **kwargs):
        return active_tdl

    async def fake_update_open_tdl_from_follow_up(session, tdl_id, payload, actor_id):
        active_tdl.due_at = payload.due_at or active_tdl.due_at
        active_tdl.completion_criteria = payload.completion_criteria or active_tdl.completion_criteria
        return active_tdl

    synced = []

    async def fake_sync_calendar_due_at_change_best_effort(session, tdl, *, actor_id, client=None):
        synced.append((tdl.tdl_id, actor_id))
        return tdl

    class ActiveCorrectionAIClient(FakeAIClient):
        async def extract_tdl_follow_up(
            self,
            *,
            draft_title: str,
            source_text: str,
        ) -> TDLFollowUpDraft:
            return TDLFollowUpDraft(
                is_follow_up=True,
                due_at=datetime(2026, 5, 22, 0, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria="每个人摸完后都有完成的表格",
                confidence=0.92,
            )

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_incomplete_draft",
        fake_find_latest_incomplete_draft,
    )
    monkeypatch.setattr(
        "app.services.intake_service.find_latest_recent_open_tdl",
        fake_find_latest_recent_open_tdl,
    )
    monkeypatch.setattr(
        "app.services.intake_service.update_open_tdl_from_follow_up",
        fake_update_open_tdl_from_follow_up,
    )
    monkeypatch.setattr(
        "app.services.intake_service.sync_calendar_due_at_change_best_effort",
        fake_sync_calendar_due_at_change_best_effort,
    )

    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-correct-active-fields",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="刚才那条时间不是今天，是明天，而且完成标准是每个人摸完后都有完成的表格",
        ),
        ActiveCorrectionAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "已创建 TDL"
    assert "2026-05-22 18:00" in card.body[1]
    assert active_tdl.completion_criteria == "每个人摸完后都有完成的表格"
    assert synced == [(active_tdl.tdl_id, "0617564550-1513038363")]


@pytest.mark.asyncio
async def test_intake_overwrites_due_at_from_explicit_correction(monkeypatch) -> None:
    session = FakeSession()
    draft = TDL(
        tdl_id=uuid4(),
        title="提交复盘方案",
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 20, 18, 0, tzinfo=SHANGHAI_TZ),
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
        return draft

    class DueCorrectionAIClient(FakeAIClient):
        async def extract_tdl_follow_up(
            self,
            *,
            draft_title: str,
            source_text: str,
        ) -> TDLFollowUpDraft:
            return TDLFollowUpDraft(
                is_follow_up=True,
                due_at=datetime(2026, 5, 21, 0, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria=None,
                confidence=0.93,
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
            message_id="msg-correct-due-at",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="刚才那条时间不是今天，是明天",
        ),
        DueCorrectionAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "2026-05-21 18:00" in card.body[2]


@pytest.mark.asyncio
async def test_intake_overwrites_completion_criteria_from_explicit_correction(monkeypatch) -> None:
    session = FakeSession()
    draft = TDL(
        tdl_id=uuid4(),
        title="提交复盘方案",
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 20, 18, 0, tzinfo=SHANGHAI_TZ),
        completion_criteria="形成口头反馈",
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_incomplete_draft(*args, **kwargs):
        return draft

    async def fake_update_draft_tdl(session, tdl_id, payload, actor_id):
        draft.completion_criteria = payload.completion_criteria
        return draft

    class CriteriaCorrectionAIClient(FakeAIClient):
        async def extract_tdl_follow_up(
            self,
            *,
            draft_title: str,
            source_text: str,
        ) -> TDLFollowUpDraft:
            return TDLFollowUpDraft(
                is_follow_up=True,
                due_at=None,
                completion_criteria="形成一页结论",
                confidence=0.94,
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
            message_id="msg-correct-criteria",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="刚才那条完成标准改成形成一页结论",
        ),
        CriteriaCorrectionAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "形成一页结论" in card.body[4]


@pytest.mark.asyncio
async def test_intake_fuzzy_matches_assigned_owner_from_voice_transcript() -> None:
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-fuzzy-owner",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="请李祯下周三前提交续费复盘",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="提交续费复盘",
                owner_id=None,
                due_at=datetime(2026, 5, 20, 18, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria=None,
                priority="P1",
                confidence=0.92,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "负责人：李珍 / Helen" in card.body


@pytest.mark.asyncio
async def test_intake_normalizes_date_only_follow_up_to_end_of_workday(monkeypatch) -> None:
    session = FakeSession()
    draft = TDL(
        tdl_id=uuid4(),
        title="复盘试听课转化",
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
                due_at=datetime(2026, 5, 18, 0, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria="形成一页结论",
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
            message_id="msg-date-follow-up",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="下周一前完成，完成标准是形成一页结论",
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
    assert "2026-05-18 18:00" in card.body[2]


@pytest.mark.asyncio
async def test_intake_confirms_latest_recent_draft_from_direct_text_command(monkeypatch) -> None:
    draft = TDL(
        tdl_id=uuid4(),
        title="前往钻石校区教团队使用 Claude",
        owner_id="0617564550-1513038363",
        due_at=datetime(2026, 5, 17, 17, 0, tzinfo=SHANGHAI_TZ),
        completion_criteria="能独立操作基础功能",
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_recent_draft(*args, **kwargs):
        return draft

    async def fake_confirm_tdl_with_calendar(session, tdl_id, actor_id):
        draft.status = "active"
        return draft

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_recent_draft",
        fake_find_latest_recent_draft,
    )
    monkeypatch.setattr(
        "app.services.intake_service.confirm_tdl_with_calendar",
        fake_confirm_tdl_with_calendar,
    )

    card = await intake_dingtalk_message(
        FakeSession(),
        DingTalkIncomingMessage(
            message_id="msg-confirm-command",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="确认创建",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "已创建 TDL"
    assert draft.status == "active"


@pytest.mark.asyncio
async def test_intake_ignores_latest_recent_draft_from_direct_text_command(monkeypatch) -> None:
    draft = TDL(
        tdl_id=uuid4(),
        title="前往钻石校区教团队使用 Claude",
        owner_id="0617564550-1513038363",
        due_at=None,
        completion_criteria=None,
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_recent_draft(*args, **kwargs):
        return draft

    async def fake_cancel_draft_tdl(session, tdl_id, actor_id):
        draft.status = "canceled"
        return draft

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_recent_draft",
        fake_find_latest_recent_draft,
    )
    monkeypatch.setattr(
        "app.services.intake_service.cancel_draft_tdl",
        fake_cancel_draft_tdl,
    )

    card = await intake_dingtalk_message(
        FakeSession(),
        DingTalkIncomingMessage(
            message_id="msg-ignore-command",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="忽略",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "已忽略草稿"
    assert draft.status == "canceled"


@pytest.mark.asyncio
async def test_intake_ignores_latest_recent_draft_from_natural_cancel_command(monkeypatch) -> None:
    draft = TDL(
        tdl_id=uuid4(),
        title="前往钻石校区教团队使用 Claude",
        owner_id="0617564550-1513038363",
        due_at=None,
        completion_criteria=None,
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_recent_draft(*args, **kwargs):
        return draft

    async def fake_cancel_draft_tdl(session, tdl_id, actor_id):
        draft.status = "canceled"
        return draft

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_recent_draft",
        fake_find_latest_recent_draft,
    )
    monkeypatch.setattr(
        "app.services.intake_service.cancel_draft_tdl",
        fake_cancel_draft_tdl,
    )

    card = await intake_dingtalk_message(
        FakeSession(),
        DingTalkIncomingMessage(
            message_id="msg-natural-cancel-command",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="刚才那条不用建了",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "已忽略草稿"
    assert draft.status == "canceled"


@pytest.mark.asyncio
async def test_intake_normalizes_unsupported_p0_when_missing_explicit_urgency() -> None:
    """AI may infer P0 from a bare "today" mention, but that alone is not enough.
    Without explicit urgency keywords, P0 should normalize down to P1 (has due_at)
    or P2 (no due_at). This test covers the P0→P1 case."""
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-relaxed-today",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="今天整理一下课件材料",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="整理课件材料",
                owner_id=None,
                due_at=datetime(2026, 5, 17, 18, 0, tzinfo=SHANGHAI_TZ),
                completion_criteria=None,
                priority="P0",
                confidence=0.70,  # below auto-create threshold so we get a draft card
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert "优先级：P1" in card.body


@pytest.mark.asyncio
async def test_intake_normalizes_unsupported_p0_to_p2_when_no_due_at() -> None:
    """P0 without due_at and without urgency → P2 (general planned item)."""
    session = FakeSession()
    card = await intake_dingtalk_message(
        session,
        DingTalkIncomingMessage(
            message_id="msg-no-date-p0",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="抽空看看课表要不要调整",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="检查课表调整",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P0",
                confidence=0.50,
            )
        ),
    )

    assert "优先级：P2" in card.body


@pytest.mark.asyncio
async def test_intake_command_confirm_on_incomplete_draft_returns_draft_card(monkeypatch) -> None:
    """When a user texts "确认创建" but the draft is still missing required fields,
    confirm_tdl_with_calendar raises ValueError and we fall back to showing the draft card."""
    draft = TDL(
        tdl_id=uuid4(),
        title="整理标准化流程文档",
        owner_id="0617564550-1513038363",
        due_at=None,  # missing – draft is incomplete
        completion_criteria=None,
        priority="P2",
        created_by="0617564550-1513038363",
        source="dingtalk_msg",
        status="draft",
    )

    async def fake_find_latest_recent_draft(*args, **kwargs):
        return draft

    async def fake_confirm_tdl_with_calendar(session, tdl_id, actor_id):
        raise ValueError("TDL is not complete")

    monkeypatch.setattr(
        "app.services.intake_service.find_latest_recent_draft",
        fake_find_latest_recent_draft,
    )
    monkeypatch.setattr(
        "app.services.intake_service.confirm_tdl_with_calendar",
        fake_confirm_tdl_with_calendar,
    )

    card = await intake_dingtalk_message(
        FakeSession(),
        DingTalkIncomingMessage(
            message_id="msg-confirm-incomplete",
            sender_id="0617564550-1513038363",
            sender_nick="Frank",
            content="确认创建",
        ),
        FakeAIClient(
            TDLFieldDraft(
                title="不该新建",
                owner_id=None,
                due_at=None,
                completion_criteria=None,
                priority="P2",
                confidence=0.0,
            )
        ),
    )

    assert card.title == "TDL 草稿"
    assert card.status == "draft"
    assert draft.status == "draft"  # not confirmed, not canceled
