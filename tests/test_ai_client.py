import pytest

from app.integrations.ai_client import PlaceholderAIClient


@pytest.mark.asyncio
async def test_placeholder_ai_client_extracts_first_line() -> None:
    drafts = await PlaceholderAIClient().extract_meeting_decisions(
        "完成 6 月续费方案\n补充试听课跟进节奏"
    )

    assert len(drafts) == 1
    assert drafts[0].title == "完成 6 月续费方案"
