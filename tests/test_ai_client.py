import pytest
from datetime import datetime
from types import SimpleNamespace

from app.integrations.ai_client import (
    ExtractedDecision,
    MeetingExtractionError,
    PlaceholderAIClient,
    ProviderAIClient,
    _to_decision_drafts,
)


@pytest.mark.asyncio
async def test_placeholder_ai_client_extracts_first_line() -> None:
    drafts = await PlaceholderAIClient().extract_meeting_decisions(
        "完成 6 月续费方案\n补充试听课跟进节奏"
    )

    assert len(drafts) == 1
    assert drafts[0].title == "完成 6 月续费方案"


def test_to_decision_drafts_resolves_known_owner() -> None:
    drafts = _to_decision_drafts(
        [
            ExtractedDecision(
                title="统一 6 月续费目标",
                owner_name="时颖",
                completion_criteria="提交续费方案",
                tdl_title="提交 6 月续费方案",
                due_at=datetime(2026, 6, 1, 18, 0),
            )
        ]
    )

    assert drafts[0].owner_id == "0962151633-1819579479"
    assert drafts[0].due_at is not None
    assert drafts[0].due_at.tzinfo is not None


class FakeResponsesAPI:
    def __init__(self, *, output_text: str = "", error: Exception | None = None) -> None:
        self.output_text = output_text
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_text=self.output_text)


class FakeOpenAIClient:
    def __init__(self, responses_api: FakeResponsesAPI) -> None:
        self.responses = responses_api


class FakeDeepSeekCompletions:
    def __init__(self, *, content: str = "备用摘要") -> None:
        self.calls = []
        self.content = content

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeDeepSeekClient:
    def __init__(self, *, content: str = "备用摘要") -> None:
        self.chat = SimpleNamespace(completions=FakeDeepSeekCompletions(content=content))


@pytest.mark.asyncio
async def test_provider_ai_client_uses_structured_openai_request() -> None:
    responses_api = FakeResponsesAPI(
        output_text='{"decisions":[{"title":"统一目标","owner_name":"时颖","completion_criteria":null,"tdl_title":"提交方案","due_at":null}]}'
    )
    client = ProviderAIClient(
        openai_client=FakeOpenAIClient(responses_api),
        deepseek_client=FakeDeepSeekClient(),
    )

    drafts = await client.extract_meeting_decisions("统一目标")

    assert drafts[0].owner_id == "0962151633-1819579479"
    assert responses_api.calls[0]["text"]["format"]["type"] == "json_schema"
    assert responses_api.calls[0]["text"]["format"]["name"] == "meeting_extraction"
    assert responses_api.calls[0]["text"]["format"]["strict"] is True


@pytest.mark.asyncio
async def test_provider_ai_client_extracts_tdl_fields_with_structured_output() -> None:
    responses_api = FakeResponsesAPI(
        output_text='{"title":"审核暑期班方案","owner_name":null,"due_at":"2026-05-20T18:00:00+08:00","completion_criteria":"形成最终审核意见","priority":"P1","confidence":0.92}'
    )
    client = ProviderAIClient(
        openai_client=FakeOpenAIClient(responses_api),
        deepseek_client=FakeDeepSeekClient(),
    )

    draft = await client.extract_tdl_fields("下周三前审核暑期班方案")

    assert draft.title == "审核暑期班方案"
    assert draft.owner_id is None
    assert draft.due_at is not None
    assert draft.completion_criteria == "形成最终审核意见"
    assert draft.priority == "P1"
    assert draft.confidence == 0.92
    assert responses_api.calls[0]["text"]["format"]["name"] == "tdl_extraction"


@pytest.mark.asyncio
async def test_provider_ai_client_does_not_fallback_on_critical_extraction() -> None:
    responses_api = FakeResponsesAPI(error=RuntimeError("openai down"))
    deepseek_client = FakeDeepSeekClient()
    client = ProviderAIClient(
        openai_client=FakeOpenAIClient(responses_api),
        deepseek_client=deepseek_client,
    )

    with pytest.raises(MeetingExtractionError):
        await client.extract_meeting_decisions("统一目标")

    assert deepseek_client.chat.completions.calls == []


@pytest.mark.asyncio
async def test_provider_ai_client_uses_deepseek_for_non_critical_fallback() -> None:
    responses_api = FakeResponsesAPI(error=RuntimeError("openai down"))
    deepseek_client = FakeDeepSeekClient()
    client = ProviderAIClient(
        openai_client=FakeOpenAIClient(responses_api),
        deepseek_client=deepseek_client,
    )

    summary = await client.summarize_text("写一条提醒")

    assert summary == "备用摘要"
    assert deepseek_client.chat.completions.calls[0]["messages"][0]["content"] == "写一条提醒"


@pytest.mark.asyncio
async def test_provider_ai_client_falls_back_to_deepseek_for_daily_intake() -> None:
    responses_api = FakeResponsesAPI(error=RuntimeError("openai down"))
    deepseek_client = FakeDeepSeekClient(
        content='{"title":"审核暑期班方案","owner_name":null,"due_at":"2026-05-20T18:00:00+08:00","completion_criteria":"形成最终审核意见","priority":"P1","confidence":0.91}'
    )
    client = ProviderAIClient(
        openai_client=FakeOpenAIClient(responses_api),
        deepseek_client=deepseek_client,
    )

    draft = await client.extract_tdl_fields("下周三前审核暑期班方案")

    assert draft.title == "审核暑期班方案"
    assert draft.priority == "P1"
    assert draft.completion_criteria == "形成最终审核意见"
    assert deepseek_client.chat.completions.calls[0]["response_format"] == {
        "type": "json_object"
    }


@pytest.mark.asyncio
async def test_provider_ai_client_extracts_tdl_follow_up_with_structured_output() -> None:
    responses_api = FakeResponsesAPI(
        output_text='{"is_follow_up":true,"due_at":"2026-05-16T16:00:00+08:00","completion_criteria":"教会基础操作","confidence":0.94}'
    )
    client = ProviderAIClient(
        openai_client=FakeOpenAIClient(responses_api),
        deepseek_client=FakeDeepSeekClient(),
    )

    draft = await client.extract_tdl_follow_up(
        draft_title="去钻石校区教 Claude",
        source_text="16 点前完成，完成标准是教会基础操作",
    )

    assert draft.due_at is not None
    assert draft.completion_criteria == "教会基础操作"
    assert draft.confidence == 0.94
    assert responses_api.calls[0]["text"]["format"]["name"] == "tdl_follow_up_extraction"
