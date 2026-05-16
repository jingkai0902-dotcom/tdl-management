from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings, load_yaml_config


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class AIClient(Protocol):
    async def extract_meeting_decisions(self, source_text: str) -> list["DecisionDraft"]:
        ...

    async def extract_tdl_fields(self, source_text: str) -> "TDLFieldDraft":
        ...

    async def extract_tdl_follow_up(
        self,
        *,
        draft_title: str,
        source_text: str,
    ) -> "TDLFollowUpDraft":
        ...


@dataclass(frozen=True)
class DecisionDraft:
    title: str
    owner_id: str | None
    completion_criteria: str | None
    tdl_title: str
    due_at: datetime | None


@dataclass(frozen=True)
class TDLFieldDraft:
    title: str
    owner_id: str | None
    due_at: datetime | None
    completion_criteria: str | None
    priority: str
    confidence: float


@dataclass(frozen=True)
class TDLFollowUpDraft:
    is_follow_up: bool
    due_at: datetime | None
    completion_criteria: str | None
    confidence: float


class ExtractedDecision(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    owner_name: str | None = None
    completion_criteria: str | None = None
    tdl_title: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None


class MeetingExtraction(BaseModel):
    decisions: list[ExtractedDecision] = Field(default_factory=list)


class ExtractedTDL(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    owner_name: str | None = None
    due_at: datetime | None = None
    completion_criteria: str | None = None
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedTDLFollowUp(BaseModel):
    is_follow_up: bool
    due_at: datetime | None = None
    completion_criteria: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class MeetingExtractionError(RuntimeError):
    """Raised when critical-path meeting extraction cannot be trusted."""


class TDLExtractionError(RuntimeError):
    """Raised when daily-intake extraction fails."""


def _normalize_due_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value


def _roster_name_to_user_id() -> dict[str, str]:
    roster = load_yaml_config("management_roster.yaml")
    mapping: dict[str, str] = {}
    for member in roster.get("management", []):
        user_id = member.get("dingtalk_user_id")
        if not user_id:
            continue
        for key in ("name", "english_name"):
            value = member.get(key)
            if value:
                mapping[str(value)] = str(user_id)
    return mapping


def _roster_prompt_lines() -> str:
    roster = load_yaml_config("management_roster.yaml")
    lines = []
    for member in roster.get("management", []):
        name = member.get("name")
        english_name = member.get("english_name")
        role = member.get("role")
        if english_name:
            lines.append(f"- {name} / {english_name}：{role}")
        else:
            lines.append(f"- {name}：{role}")
    return "\n".join(lines)


def _build_prompt(source_text: str) -> str:
    today = datetime.now(tz=SHANGHAI_TZ).date().isoformat()
    return f"""
你是管理层待办系统的会议纪要解析器。

今天是 {today}，时区为 Asia/Shanghai。
请从会议纪要中只提取“已经形成明确动作”的决议，不要把讨论意见、背景信息、感想当成决议。

已知负责人名单如下，owner_name 只能从这些名字中选择；如果无法确定，填 null：
{_roster_prompt_lines()}

输出要求：
1. 每条 decision 只表示一项管理决议。
2. title 是决议本身；tdl_title 是可执行动作。
3. completion_criteria 只在纪要里有明确验收标准时填写，否则填 null。
4. due_at 只有在纪要能明确推出截止时间时填写，使用 ISO 8601；无法确定就填 null，不要猜。
5. 如果纪要中没有明确决议，返回空数组。

会议纪要：
{source_text}
""".strip()


def _build_intake_prompt(source_text: str) -> str:
    today = datetime.now(tz=SHANGHAI_TZ).date().isoformat()
    return f"""
你是管理层待办系统的日常消息解析器。

今天是 {today}，时区为 Asia/Shanghai。
请把一句话整理成一个待办字段对象。

已知负责人名单如下；owner_name 只有在原文明确提到他人时才填写，否则填 null：
{_roster_prompt_lines()}

输出要求：
1. title 保留原意，但要整理成清晰、可执行的动作。
2. due_at 只有在原文能明确推出时才填写，使用 ISO 8601；无法确定就填 null。
   仅有“下午 / 晚上 / 稍后 / 回头”这类模糊说法，不足以填写 due_at。
3. completion_criteria 只有在原文明确说明“做到什么程度算完成”时才填写，否则填 null。
4. priority 只能填 P0/P1/P2/P3：
   - P0：今天必须处理，或原文明确是紧急且重要
   - P1：本周重要事项
   - P2：一般计划性事项
   - P3：可延后、低紧迫事项
   如果无法判断，填 P2。
5. confidence 表示你对字段完整性和语义判断的把握，0 到 1。
6. 不要补造负责人、截止时间、完成标准或背景。
7. 请只输出 JSON 对象，不要附加解释。

用户消息：
{source_text}
""".strip()


def _build_intake_follow_up_prompt(*, draft_title: str, source_text: str) -> str:
    today = datetime.now(tz=SHANGHAI_TZ).date().isoformat()
    return f"""
你是管理层待办系统的草稿补充识别器。

今天是 {today}，时区为 Asia/Shanghai。
已有草稿标题：{draft_title}

请判断“用户新消息”是不是在继续补充这条已有草稿，而不是新建另一条任务。

输出要求：
1. 只有当新消息主要是在补充上一条草稿的字段时，is_follow_up 才能填 true。
2. 如果新消息本身更像一条新任务，或和已有草稿关系不明确，is_follow_up 必须填 false。
3. due_at 只有在新消息能明确推出时才填写，使用 ISO 8601；无法确定就填 null。
4. completion_criteria 只有在新消息明确说明“做到什么程度算完成”时才填写，否则填 null。
5. confidence 表示你对“这是补充消息”的判断把握，0 到 1。
6. 不要补造截止时间或完成标准。
7. 请只输出 JSON 对象，不要附加解释。

用户新消息：
{source_text}
""".strip()


def _meeting_json_schema() -> dict[str, Any]:
    return {
        "name": "meeting_extraction",
        "schema": MeetingExtraction.model_json_schema(),
        "strict": True,
    }


def _tdl_json_schema() -> dict[str, Any]:
    return {
        "name": "tdl_extraction",
        "schema": ExtractedTDL.model_json_schema(),
        "strict": True,
    }


def _tdl_follow_up_json_schema() -> dict[str, Any]:
    return {
        "name": "tdl_follow_up_extraction",
        "schema": ExtractedTDLFollowUp.model_json_schema(),
        "strict": True,
    }


def _to_decision_drafts(items: Iterable[ExtractedDecision]) -> list[DecisionDraft]:
    name_to_id = _roster_name_to_user_id()
    return [
        DecisionDraft(
            title=item.title,
            owner_id=name_to_id.get(item.owner_name or ""),
            completion_criteria=item.completion_criteria,
            tdl_title=item.tdl_title,
            due_at=_normalize_due_at(item.due_at),
        )
        for item in items
    ]


def _to_tdl_field_draft(item: ExtractedTDL) -> TDLFieldDraft:
    return TDLFieldDraft(
        title=item.title,
        owner_id=_roster_name_to_user_id().get(item.owner_name or ""),
        due_at=_normalize_due_at(item.due_at),
        completion_criteria=item.completion_criteria,
        priority=item.priority,
        confidence=item.confidence,
    )


def _to_tdl_follow_up_draft(item: ExtractedTDLFollowUp) -> TDLFollowUpDraft:
    return TDLFollowUpDraft(
        is_follow_up=item.is_follow_up,
        due_at=_normalize_due_at(item.due_at),
        completion_criteria=item.completion_criteria,
        confidence=item.confidence,
    )


class ProviderAIClient:
    """OpenAI primary client with optional DeepSeek fallback for non-critical work."""

    def __init__(
        self,
        openai_client: AsyncOpenAI | None = None,
        deepseek_client: AsyncOpenAI | None = None,
    ) -> None:
        settings = get_settings()
        self.openai_model = settings.openai_model
        self.deepseek_model = settings.deepseek_model
        self.openai_client = openai_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self.deepseek_client = deepseek_client or AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )

    async def extract_meeting_decisions(self, source_text: str) -> list[DecisionDraft]:
        """Critical path: OpenAI only. Do not silently degrade extraction quality."""
        prompt = _build_prompt(source_text)
        try:
            response = await self.openai_client.responses.create(
                model=self.openai_model,
                input=prompt,
                text={"format": {"type": "json_schema", **_meeting_json_schema()}},
            )
            if not response.output_text:
                raise MeetingExtractionError("OpenAI returned an empty extraction payload")
            payload = MeetingExtraction.model_validate_json(response.output_text)
        except MeetingExtractionError:
            raise
        except ValidationError as exc:
            raise MeetingExtractionError("OpenAI returned invalid extraction JSON") from exc
        except Exception as exc:
            raise MeetingExtractionError("OpenAI extraction request failed") from exc
        return _to_decision_drafts(payload.decisions)

    async def extract_tdl_fields(self, source_text: str) -> TDLFieldDraft:
        prompt = _build_intake_prompt(source_text)
        try:
            response = await self.openai_client.responses.create(
                model=self.openai_model,
                input=prompt,
                text={"format": {"type": "json_schema", **_tdl_json_schema()}},
            )
            if not response.output_text:
                raise TDLExtractionError("OpenAI returned an empty TDL extraction payload")
            payload = ExtractedTDL.model_validate_json(response.output_text)
        except Exception:
            payload = await self._extract_tdl_fields_with_deepseek(prompt)
        return _to_tdl_field_draft(payload)

    async def extract_tdl_follow_up(
        self,
        *,
        draft_title: str,
        source_text: str,
    ) -> TDLFollowUpDraft:
        prompt = _build_intake_follow_up_prompt(
            draft_title=draft_title,
            source_text=source_text,
        )
        try:
            response = await self.openai_client.responses.create(
                model=self.openai_model,
                input=prompt,
                text={"format": {"type": "json_schema", **_tdl_follow_up_json_schema()}},
            )
            if not response.output_text:
                raise TDLExtractionError("OpenAI returned an empty TDL follow-up payload")
            payload = ExtractedTDLFollowUp.model_validate_json(response.output_text)
        except Exception:
            payload = await self._extract_tdl_follow_up_with_deepseek(prompt)
        return _to_tdl_follow_up_draft(payload)

    async def _extract_tdl_fields_with_deepseek(self, prompt: str) -> ExtractedTDL:
        try:
            response = await self.deepseek_client.chat.completions.create(
                model=self.deepseek_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            return ExtractedTDL.model_validate_json(content)
        except ValidationError as exc:
            raise TDLExtractionError("DeepSeek returned invalid TDL extraction JSON") from exc
        except Exception as exc:
            raise TDLExtractionError("DeepSeek TDL extraction request failed") from exc

    async def _extract_tdl_follow_up_with_deepseek(
        self,
        prompt: str,
    ) -> ExtractedTDLFollowUp:
        try:
            response = await self.deepseek_client.chat.completions.create(
                model=self.deepseek_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            return ExtractedTDLFollowUp.model_validate_json(content)
        except ValidationError as exc:
            raise TDLExtractionError("DeepSeek returned invalid TDL follow-up JSON") from exc
        except Exception as exc:
            raise TDLExtractionError("DeepSeek TDL follow-up request failed") from exc

    async def summarize_text(self, text: str, *, allow_fallback: bool = True) -> str:
        """Non-critical helper reserved for reminder copy and summaries."""
        try:
            response = await self.openai_client.responses.create(
                model=self.openai_model,
                input=text,
            )
            return response.output_text
        except Exception:
            if not allow_fallback:
                raise
        response = await self.deepseek_client.chat.completions.create(
            model=self.deepseek_model,
            messages=[{"role": "user", "content": text}],
        )
        return response.choices[0].message.content or ""


class PlaceholderAIClient:
    """Deterministic fallback used when provider credentials are not configured."""

    async def extract_meeting_decisions(self, source_text: str) -> list[DecisionDraft]:
        lines = [line.strip("- ").strip() for line in source_text.splitlines() if line.strip()]
        if not lines:
            return []
        first_line = lines[0][:500]
        return [
            DecisionDraft(
                title=first_line,
                owner_id=None,
                completion_criteria=None,
                tdl_title=first_line,
                due_at=None,
            )
        ]

    async def extract_tdl_fields(self, source_text: str) -> TDLFieldDraft:
        return TDLFieldDraft(
            title=source_text.strip()[:500],
            owner_id=None,
            due_at=None,
            completion_criteria=None,
            priority="P2",
            confidence=0.0,
        )

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


def get_ai_client() -> AIClient:
    settings = get_settings()
    if settings.openai_api_key:
        return ProviderAIClient()
    return PlaceholderAIClient()
