from dataclasses import replace
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.ai_client import AIClient, TDLExtractionError, TDLFieldDraft, get_ai_client
from app.integrations.dingtalk_card import TDLCard, build_created_card, build_draft_card
from app.schemas import DingTalkIncomingMessage, TDLCreate, TDLDraftCreate, TDLDraftUpdate
from app.services.calendar_service import create_tdl_with_calendar
from app.services.tdl_service import (
    create_draft_tdl,
    find_latest_incomplete_draft,
    update_draft_tdl,
)


def _auto_create_rules() -> dict:
    return load_yaml_config("tdl_rules.yaml").get("auto_create", {})


def _follow_up_rules() -> dict:
    return load_yaml_config("tdl_rules.yaml").get("follow_up", {})


def _management_aliases_by_user_id() -> dict[str, set[str]]:
    roster = load_yaml_config("management_roster.yaml")
    aliases_by_user_id: dict[str, set[str]] = {}
    for member in roster.get("management", []):
        user_id = member.get("dingtalk_user_id")
        if not user_id:
            continue
        aliases = {
            str(value)
            for key in ("name", "english_name")
            if (value := member.get(key))
        }
        if aliases:
            aliases_by_user_id[str(user_id)] = aliases
    return aliases_by_user_id


def _mentioned_other_management_ids(source_text: str, *, sender_id: str) -> set[str]:
    return {
        user_id
        for user_id, aliases in _management_aliases_by_user_id().items()
        if user_id != sender_id and any(alias in source_text for alias in aliases)
    }


def _infer_assigned_owner_id(source_text: str, *, sender_id: str) -> str | None:
    candidates = []
    for user_id, aliases in _management_aliases_by_user_id().items():
        if user_id == sender_id:
            continue
        for alias in aliases:
            assignment_patterns = (
                rf"(?:让|请|由)\s*{re.escape(alias)}",
                rf"{re.escape(alias)}\s*(?:负责|跟进|完成|提交|梳理|输出)",
            )
            if any(re.search(pattern, source_text) for pattern in assignment_patterns):
                candidates.append(user_id)
                break
    unique_candidates = set(candidates)
    if len(unique_candidates) == 1:
        return unique_candidates.pop()
    return None


def _has_explicit_due_reference(source_text: str) -> bool:
    normalized = source_text.replace(" ", "")
    patterns = (
        r"\d{1,2}(?::\d{2})?(?:点|时)",
        r"\d{1,2}月\d{1,2}[日号]?",
        r"\d{1,2}[日号]",
        r"(今天|明天|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天])",
        r"(截止|截至|月底|月内)",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _drop_unsupported_due_at(
    extracted: TDLFieldDraft,
    *,
    source_text: str,
) -> TDLFieldDraft:
    if extracted.due_at is None or _has_explicit_due_reference(source_text):
        return extracted
    return replace(extracted, due_at=None)


async def intake_dingtalk_message(
    session: AsyncSession,
    message: DingTalkIncomingMessage,
    ai_client: AIClient | None = None,
) -> TDLCard:
    client = ai_client or get_ai_client()
    follow_up_rules = _follow_up_rules()
    latest_draft = await find_latest_incomplete_draft(
        session,
        created_by=message.sender_id,
        max_age_minutes=int(follow_up_rules.get("max_age_minutes", 15)),
    )
    if latest_draft is not None:
        try:
            follow_up = await client.extract_tdl_follow_up(
                draft_title=latest_draft.title,
                source_text=message.content,
            )
        except TDLExtractionError:
            follow_up = None
        if (
            follow_up is not None
            and follow_up.is_follow_up
            and follow_up.confidence
            >= float(follow_up_rules.get("minimum_confidence", 0.80))
        ):
            updates = TDLDraftUpdate(
                due_at=follow_up.due_at if latest_draft.due_at is None else None,
                completion_criteria=(
                    follow_up.completion_criteria
                    if latest_draft.completion_criteria is None
                    else None
                ),
            )
            if updates.model_dump(exclude_none=True):
                tdl = await update_draft_tdl(
                    session,
                    latest_draft.tdl_id,
                    updates,
                    message.sender_id,
                )
                return build_draft_card(tdl)

    try:
        extracted = await client.extract_tdl_fields(message.content)
    except TDLExtractionError:
        extracted = TDLFieldDraft(
            title=message.content.strip()[:500],
            owner_id=None,
            due_at=None,
            completion_criteria=None,
            priority="P2",
            confidence=0.0,
        )
    extracted = _drop_unsupported_due_at(extracted, source_text=message.content)
    mentioned_other_ids = _mentioned_other_management_ids(
        message.content,
        sender_id=message.sender_id,
    )
    inferred_owner_id = _infer_assigned_owner_id(
        message.content,
        sender_id=message.sender_id,
    )
    owner_id = extracted.owner_id or inferred_owner_id
    if owner_id is None and not mentioned_other_ids:
        owner_id = message.sender_id
    payload = TDLDraftCreate(
        title=extracted.title,
        owner_id=owner_id,
        due_at=extracted.due_at,
        created_by=message.sender_id,
        source="dingtalk_msg",
        raw_text=message.content,
        completion_criteria=extracted.completion_criteria,
        priority=extracted.priority,
        confidence=extracted.confidence,
    )

    rules = _auto_create_rules()
    minimum_confidence = float(rules.get("minimum_confidence", 0.85))
    require_due_at = bool(rules.get("require_due_at", True))
    allow_if_involves_others = bool(rules.get("allow_if_involves_others", False))
    involves_others = bool(mentioned_other_ids) or (
        owner_id is not None and owner_id != message.sender_id
    )
    can_auto_create = (
        (allow_if_involves_others or not involves_others)
        and (not require_due_at or extracted.due_at is not None)
        and extracted.confidence >= minimum_confidence
    )
    if can_auto_create:
        create_payload = TDLCreate(
            title=payload.title,
            owner_id=payload.owner_id,
            due_at=payload.due_at,
            created_by=payload.created_by,
            participants=payload.participants,
            priority=payload.priority,
            completion_criteria=payload.completion_criteria,
            source=payload.source,
        )
        tdl = await create_tdl_with_calendar(session, create_payload)
        return build_created_card(tdl)

    tdl = await create_draft_tdl(session, payload)
    return build_draft_card(tdl)
