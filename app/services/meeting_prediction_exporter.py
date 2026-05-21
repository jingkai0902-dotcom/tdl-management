from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.meeting_evaluator import (
    ALLOWED_MATURITIES,
    ALLOWED_OBJECT_TYPES,
    MeetingClassificationItem,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class MeetingPredictionPayload(BaseModel):
    item_id: str = Field(min_length=1)
    maturity: str
    object_type: str
    tdl_eligible: bool
    evidence_span: str
    summary: str = ""
    what: str = ""
    who: str = ""
    when_value: str = ""
    evidence_for_what: str = ""
    evidence_for_who: str = ""
    evidence_for_when: str = ""


@dataclass(frozen=True)
class ModelProviderConfig:
    provider: str
    model: str
    api_key: str
    base_url: str


def resolve_provider_config(
    *,
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ModelProviderConfig:
    normalized_provider = provider.lower().strip()
    settings = get_settings()

    if normalized_provider == "deepseek":
        resolved_model = model or settings.deepseek_model
        resolved_key = api_key or settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")
        resolved_base_url = base_url or "https://api.deepseek.com"
    elif normalized_provider == "llama":
        resolved_model = model or os.getenv("LLAMA_MODEL", "llama-3.1-70b-versatile")
        resolved_key = api_key or os.getenv("LLAMA_API_KEY", "")
        resolved_base_url = base_url or os.getenv("LLAMA_BASE_URL", "")
    else:
        raise ValueError("provider must be one of: deepseek, llama")

    if not resolved_key:
        key_name = "DEEPSEEK_API_KEY" if normalized_provider == "deepseek" else "LLAMA_API_KEY"
        raise ValueError(f"Missing API key. Set {key_name} or pass --api-key.")
    if not resolved_base_url:
        raise ValueError("Missing base URL. Pass --base-url or set LLAMA_BASE_URL.")

    return ModelProviderConfig(
        provider=normalized_provider,
        model=resolved_model,
        api_key=resolved_key,
        base_url=resolved_base_url,
    )


def build_prediction_prompt(row: dict[str, Any]) -> str:
    item_id = str(row.get("item_id") or "").strip()
    source_id = str(row.get("source_id") or "").strip()
    source_type = str(row.get("source_type") or "").strip()
    locator = str(row.get("evidence_locator") or "").strip()
    fragment = str(row.get("summary") or row.get("evidence_span") or "").strip()
    today = datetime.now(tz=SHANGHAI_TZ).date().isoformat()

    return f"""
你是 TDL 管理系统的会议内容严格分类器。

今天是 {today}，时区为 Asia/Shanghai。
请只根据给定片段分类，不要使用外部知识补全事实，不要把方向、倡导、讨论包装成已决议。

允许的 maturity：
- fact：客观事实或状态陈述
- confirmed：会议中已经形成明确处理方向或明确动作
- pending：还需要继续讨论、拆解或确认的议题
- spark：想法、倡导、愿景、方法设想
- signal：风险、机会、趋势或值得后续观察的线索

允许的 object_type：
- Fact
- Task
- Decision
- Issue
- Idea
- Signal

关键边界：
1. fact 表示单纯客观事实；signal 表示事实背后已经暴露风险、机会、趋势、异常或管理关注点。
   如果片段只是一个明确的单点数据、对比数据或排名数据，先判为 fact + Fact，例如“15比12”“缩减48%”“最低con率15%”这类可核验指标本身。
   如果片段包含“正在下滑 / 风险 / 可能正在形成 / 关注点转向 / 收口不严 / 反复出现 / 氛围变化 / 管理期待已经出现”等趋势、异常、归纳或管理含义，判为 signal + Signal。
   如果 source_id 是 multi_source 或 source_type 是 derived_note，且片段是跨材料归纳，优先判为 signal + Signal。
2. Decision 表示已经形成处理方向或推进判断，但还不是具体执行动作。
   如果片段只是“继续推进 / 往前推 / 进入常态化 / 优先从某方向切入”，且没有明确负责人和截止时间，判为 confirmed + Decision，不能判为 Task。
3. Task 只能用于会议已经明确交代执行动作，并且原片段同时具备 what、who、when_value。
4. spark 表示尚未发生的想法、倡导、愿景或方法设想；如果片段说的是会议中已经出现的管理期待、组织氛围变化或使用趋势，优先判为 signal，不要判为 spark。

TDL 资格规则：
1. tdl_eligible=true 只能用于 confirmed + Task。
2. confirmed + Task 必须同时具备 what、who、when_value；缺任一项则 tdl_eligible=false。
3. 不要猜负责人、截止时间或完成标准。原片段没有明确说出时，对应字段填空字符串。
4. spark + Task、signal + Task 不允许。

请输出单个 JSON 对象，不要附加解释。字段必须为：
item_id, maturity, object_type, tdl_eligible, evidence_span, summary,
what, who, when_value, evidence_for_what, evidence_for_who, evidence_for_when

输入片段：
- item_id：{item_id}
- source_id：{source_id}
- source_type：{source_type}
- evidence_locator：{locator}
- fragment：{fragment}
""".strip()


def prediction_from_payload(payload: str, *, expected_item_id: str) -> MeetingClassificationItem:
    parsed = MeetingPredictionPayload.model_validate(_parse_json_object(payload))
    if parsed.item_id != expected_item_id:
        raise ValueError(
            f"Model returned item_id={parsed.item_id!r}, expected {expected_item_id!r}"
        )
    if parsed.maturity not in ALLOWED_MATURITIES:
        raise ValueError(f"Invalid maturity: {parsed.maturity!r}")
    if parsed.object_type not in ALLOWED_OBJECT_TYPES:
        raise ValueError(f"Invalid object_type: {parsed.object_type!r}")

    return MeetingClassificationItem(
        item_id=parsed.item_id,
        maturity=parsed.maturity,
        object_type=parsed.object_type,
        tdl_eligible=parsed.tdl_eligible,
        evidence_span=parsed.evidence_span,
        summary=parsed.summary,
        what=parsed.what,
        who=parsed.who,
        when_value=parsed.when_value,
        evidence_for_what=parsed.evidence_for_what,
        evidence_for_who=parsed.evidence_for_who,
        evidence_for_when=parsed.evidence_for_when,
    )


def item_to_jsonable(item: MeetingClassificationItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "maturity": item.maturity,
        "object_type": item.object_type,
        "tdl_eligible": item.tdl_eligible,
        "evidence_span": item.evidence_span,
        "summary": item.summary,
        "what": item.what,
        "who": item.who,
        "when_value": item.when_value,
        "evidence_for_what": item.evidence_for_what,
        "evidence_for_who": item.evidence_for_who,
        "evidence_for_when": item.evidence_for_when,
    }


async def request_prediction(
    *,
    client: AsyncOpenAI,
    model: str,
    row: dict[str, Any],
) -> MeetingClassificationItem:
    prompt = build_prediction_prompt(row)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    if response is None or not getattr(response, "choices", None):
        raise ValueError("Model returned an empty response")
    content = response.choices[0].message.content or ""
    return prediction_from_payload(
        content,
        expected_item_id=str(row.get("item_id") or "").strip(),
    )


def make_output_payload(
    *,
    provider_config: ModelProviderConfig,
    gold_path: Path,
    items: list[MeetingClassificationItem],
) -> dict[str, Any]:
    return {
        "metadata": {
            "provider": provider_config.provider,
            "model": provider_config.model,
            "gold_path": str(gold_path),
            "generated_at": datetime.now(tz=SHANGHAI_TZ).isoformat(),
            "item_count": len(items),
        },
        "items": [item_to_jsonable(item) for item in items],
    }


def _parse_json_object(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", payload, flags=re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Model prediction must be a JSON object")
    return parsed
