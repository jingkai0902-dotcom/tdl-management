from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.dingtalk_webhook import confirm_action, update_draft_action
from app.schemas import DingTalkAction, TDLDraftUpdate


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
