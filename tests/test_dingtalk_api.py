from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.dingtalk_webhook import batch_confirm_drafts_action, confirm_action, update_draft_action
from app.schemas import BatchConfirmDraftsRead, BatchConfirmDraftsRequest, DingTalkAction, TDLDraftUpdate, TDLRead


@pytest.mark.asyncio
async def test_confirm_action_returns_conflict_for_incomplete_draft(monkeypatch) -> None:
    async def fake_confirm_tdl(session, tdl_id, actor_id):
        raise ValueError("TDL draft missing required fields: owner_id, due_at")

    monkeypatch.setattr("app.api.dingtalk_webhook.confirm_tdl", fake_confirm_tdl)

    with pytest.raises(HTTPException) as exc:
        await confirm_action(
            DingTalkAction(action="confirm", tdl_id=uuid4(), actor_id="user-1"),
            session=None,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_draft_action_returns_updated_draft_card(monkeypatch) -> None:
    tdl_id = uuid4()

    async def fake_update_draft_tdl(session, incoming_tdl_id, payload, actor_id):
        assert incoming_tdl_id == tdl_id
        assert payload.owner_id == "0617564550-1513038363"
        return SimpleNamespace(
            tdl_id=tdl_id,
            title="排定新师培训课表",
            owner_id="0617564550-1513038363",
            due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
            priority="P2",
            status="draft",
            completion_criteria=None,
        )

    monkeypatch.setattr(
        "app.api.dingtalk_webhook.update_draft_tdl",
        fake_update_draft_tdl,
    )

    result = await update_draft_action(
        tdl_id,
        TDLDraftUpdate(
            owner_id="0617564550-1513038363",
            due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
        ),
        actor_id="0617564550-1513038363",
        session=None,
    )

    assert result.title == "TDL 草稿"
    assert "负责人：0617564550-1513038363" in result.body


@pytest.mark.asyncio
async def test_batch_confirm_drafts_action_returns_confirmed_and_skipped(monkeypatch) -> None:
    confirmed_id = uuid4()
    skipped_id = uuid4()

    async def fake_confirm_ready_drafts(session, tdl_ids, actor_id):
        assert tdl_ids == [confirmed_id, skipped_id]
        assert actor_id == "user-1"
        return BatchConfirmDraftsRead(
            confirmed=[
                TDLRead(
                    tdl_id=confirmed_id,
                    title="完成市场 SOP",
                    owner_id="user-1",
                    due_at=datetime(2026, 5, 31, 18, 0, tzinfo=UTC),
                    status="active",
                    priority="P2",
                    source="meeting_minutes",
                    missing_fields=[],
                    next_actions=["confirm"],
                )
            ],
            skipped=[
                TDLRead(
                    tdl_id=skipped_id,
                    title="排定新师培训课表",
                    owner_id=None,
                    due_at=None,
                    status="draft",
                    priority="P2",
                    source="meeting_minutes",
                    missing_fields=["owner_id", "due_at"],
                    next_actions=["set_owner", "set_due_at"],
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.dingtalk_webhook.confirm_ready_drafts",
        fake_confirm_ready_drafts,
    )

    result = await batch_confirm_drafts_action(
        BatchConfirmDraftsRequest(
            tdl_ids=[confirmed_id, skipped_id],
            actor_id="user-1",
        ),
        session=None,
    )

    assert [tdl.tdl_id for tdl in result.confirmed] == [confirmed_id]
    assert [tdl.tdl_id for tdl in result.skipped] == [skipped_id]
