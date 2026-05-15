from datetime import UTC, datetime

from app.schemas import TDLCreate


def test_tdl_create_defaults() -> None:
    payload = TDLCreate(
        title="测试待办",
        owner_id="owner-1",
        due_at=datetime(2026, 5, 20, tzinfo=UTC),
        created_by="owner-1",
    )

    assert payload.priority == "P2"
    assert payload.source == "manual"
    assert payload.participants == []
