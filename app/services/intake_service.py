from dataclasses import replace
from datetime import datetime
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_yaml_config
from app.integrations.ai_client import AIClient, TDLExtractionError, TDLFieldDraft, get_ai_client
from app.integrations.dingtalk_card import (
    TDLCard,
    build_canceled_card,
    build_created_card,
    build_draft_card,
    build_no_follow_up_target_card,
)
from app.schemas import DingTalkIncomingMessage, TDLCreate, TDLDraftCreate, TDLDraftUpdate
from app.roster import (
    management_aliases_by_user_id,
    resolve_management_user_id,
)
from app.services.calendar_service import confirm_tdl_with_calendar, create_tdl_with_calendar
from app.services.calendar_service import sync_calendar_due_at_change_best_effort
from app.services.tdl_service import (
    cancel_draft_tdl,
    create_draft_tdl,
    find_latest_incomplete_draft,
    find_latest_recent_open_tdl,
    find_latest_recent_draft,
    update_open_tdl_from_follow_up,
    update_draft_tdl,
)


def _auto_create_rules() -> dict:
    return load_yaml_config("tdl_rules.yaml").get("auto_create", {})


def _follow_up_rules() -> dict:
    return load_yaml_config("tdl_rules.yaml").get("follow_up", {})


def _management_aliases_by_user_id() -> dict[str, set[str]]:
    return management_aliases_by_user_id()


def _mentioned_other_management_ids(source_text: str, *, sender_id: str) -> set[str]:
    exact_matches = {
        user_id
        for user_id, aliases in _management_aliases_by_user_id().items()
        if user_id != sender_id and any(alias in source_text for alias in aliases)
    }
    fuzzy_match = resolve_management_user_id(source_text, exclude_user_id=sender_id)
    if fuzzy_match:
        exact_matches.add(fuzzy_match)
    return exact_matches


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
    fuzzy_candidate = resolve_management_user_id(source_text, exclude_user_id=sender_id)
    if fuzzy_candidate and re.search(r"(?:让|请|由)\s*[\u4e00-\u9fa5A-Za-z]{1,20}", source_text):
        return fuzzy_candidate
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


def _has_explicit_time_reference(source_text: str) -> bool:
    normalized = source_text.replace(" ", "")
    return bool(re.search(r"\d{1,2}(?::\d{2})?(?:点|时)", normalized))


def _has_explicit_urgency_reference(source_text: str) -> bool:
    normalized = source_text.replace(" ", "")
    patterns = (
        r"(紧急|立刻|马上|火急)",
        r"(必须|务必)(?:今天|今日)?",
        r"(今天|今日)(?:必须|务必|截止|最晚)",
        r"(最晚|截止)(?:今天|今日)",
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


def _normalize_date_only_due_at(
    due_at: datetime | None,
    *,
    source_text: str,
) -> datetime | None:
    if (
        due_at is None
        or not _has_explicit_due_reference(source_text)
        or _has_explicit_time_reference(source_text)
    ):
        return due_at
    if any((due_at.hour, due_at.minute, due_at.second, due_at.microsecond)):
        return due_at
    return due_at.replace(hour=18)


def _normalize_unsupported_p0(
    extracted: TDLFieldDraft,
    *,
    source_text: str,
) -> TDLFieldDraft:
    if extracted.priority != "P0" or _has_explicit_urgency_reference(source_text):
        return extracted
    return replace(extracted, priority="P1" if extracted.due_at is not None else "P2")


def _mentions_completion_criteria(source_text: str) -> bool:
    normalized = source_text.replace(" ", "")
    return any(
        token in normalized
        for token in ("完成标准", "完成的标准", "做到什么程度", "算完成", "验收标准")
    )


def _looks_like_draft_correction(source_text: str) -> bool:
    normalized = source_text.replace(" ", "")
    patterns = (
        r"(刚才|上面|前面|上一条).{0,12}(打错|说错|写错|错了|更正|纠正)",
        r"(不是|别写成|不要写成).{1,12}(是|改成|换成)",
        r"(改成|换成|更正为|纠正为)",
        r"(刚才|上面|前面|上一条|那条|这条|这一条).{0,20}(完成标准|完成的标准|做到什么程度|算完成|验收标准)",
        r"(刚才|上面|前面|上一条|那条).{0,12}(交给|给|由).{1,20}(负责|跟进|完成|提交|处理)?",
        r"(负责人|责任人).{0,8}(交给|给|由|改成|改为|换成)",
        r"(任务)?(负责人|责任人).{0,4}(为|是)[\u4e00-\u9fa5A-Za-z\s._-]{1,20}.{0,8}(非|不是)",
        r"^是[\u4e00-\u9fa5A-Za-z]{1,20}$",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _looks_like_contextual_follow_up(source_text: str) -> bool:
    normalized = source_text.replace(" ", "")
    patterns = (
        r"(刚才|上面|前面|上一条|那条|这条|这一条)",
        r"(补充说明|补充一下).{0,24}(负责人|责任人|完成标准|截止|时间|不是|非)",
        r"(任务)?(负责人|责任人).{0,4}(为|是)[\u4e00-\u9fa5A-Za-z\s._-]{1,20}.{0,8}(非|不是)",
        r"(不是|非)[\u4e00-\u9fa5A-Za-z\s._-]{1,20}的?.{0,8}是[\u4e00-\u9fa5A-Za-z\s._-]{1,20}的?任务",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _looks_like_draft_cancel(source_text: str) -> bool:
    normalized = _normalize_direct_command(source_text)
    if normalized in {"忽略", "取消"}:
        return True
    patterns = (
        r"(刚才|上面|前面|上一条|那条).{0,12}(取消|忽略|不要了|不用建|别建)",
        r"(取消|忽略).{0,12}(刚才|上面|前面|上一条|那条)",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _owner_id_from_correction_text(source_text: str, *, sender_id: str) -> str | None:
    if not _looks_like_draft_correction(source_text):
        return None
    candidate_texts = []
    patterns = (
        r"(?:不是|别写成|不要写成).{1,20}?(?:而是|是|改成|换成)(?P<name>[\u4e00-\u9fa5A-Za-z\s._-]{1,20})",
        r"(?:负责人|责任人)?\s*(?:改成|改为|换成|更正为|纠正为)(?P<name>[\u4e00-\u9fa5A-Za-z\s._-]{1,20})",
        r"(?:刚才|上面|前面|上一条|那条).{0,20}?(?:交给|给|由)(?P<name>[\u4e00-\u9fa5A-Za-z\s._-]{1,20})(?:负责|跟进|完成|提交|处理|的任务)?",
        r"(?:负责人|责任人).{0,8}?(?:交给|给|由)(?P<name>[\u4e00-\u9fa5A-Za-z\s._-]{1,20})(?:负责|跟进|完成|提交|处理)?",
        r"(?:任务)?(?:负责人|责任人).{0,4}(?:为|是)(?P<name>[\u4e00-\u9fa5A-Za-z\s._-]{1,20}).{0,8}(?:非|不是)",
        r"^是(?P<name>[\u4e00-\u9fa5A-Za-z\s._-]{1,20})$",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source_text.strip()):
            candidate_texts.append(match.group("name"))

    resolved_ids = [
        owner_id
        for text in candidate_texts
        if (owner_id := resolve_management_user_id(text, exclude_user_id=sender_id))
    ]
    unique_ids = set(resolved_ids)
    if len(unique_ids) == 1:
        return unique_ids.pop()
    return None


def _can_update_due_at(latest_draft, *, source_text: str, is_correction: bool) -> bool:
    return latest_draft.due_at is None or (
        is_correction and _has_explicit_due_reference(source_text)
    )


def _can_update_completion_criteria(latest_draft, *, source_text: str, is_correction: bool) -> bool:
    return latest_draft.completion_criteria is None or (
        is_correction and _mentions_completion_criteria(source_text)
    )


def _build_follow_up_updates(
    latest_tdl,
    *,
    source_text: str,
    sender_id: str,
    deterministic_owner_id: str | None,
    follow_up,
    has_confident_ai_follow_up: bool,
    is_correction: bool,
) -> TDLDraftUpdate:
    return TDLDraftUpdate(
        owner_id=(
            deterministic_owner_id
            or _follow_up_owner_id(
                source_text,
                sender_id=sender_id,
                ai_owner_id=follow_up.owner_id if follow_up is not None else None,
            )
        ),
        due_at=(
            _normalize_date_only_due_at(
                follow_up.due_at,
                source_text=source_text,
            )
            if has_confident_ai_follow_up
            and _can_update_due_at(
                latest_tdl,
                source_text=source_text,
                is_correction=is_correction,
            )
            else None
        ),
        completion_criteria=(
            follow_up.completion_criteria
            if has_confident_ai_follow_up
            and _can_update_completion_criteria(
                latest_tdl,
                source_text=source_text,
                is_correction=is_correction,
            )
            else None
        ),
    )


def _should_attempt_follow_up(
    latest_draft,
    *,
    source_text: str,
    sender_id: str,
) -> bool:
    if latest_draft is None:
        return False
    is_correction = _looks_like_draft_correction(source_text)
    # 明确提到他人但不是纠错时，通常是在创建新任务；纠错消息仍应进入 follow-up 判断。
    if not is_correction and _mentioned_other_management_ids(source_text, sender_id=sender_id):
        return False
    return (
        is_correction
        or (
            latest_draft.owner_id is None
            and resolve_management_user_id(source_text, exclude_user_id=sender_id) is not None
        )
        or (
            latest_draft.due_at is None and _has_explicit_due_reference(source_text)
        )
        or (
            latest_draft.completion_criteria is None and _mentions_completion_criteria(source_text)
        )
    )


def _follow_up_owner_id(source_text: str, *, sender_id: str, ai_owner_id: str | None) -> str | None:
    if ai_owner_id:
        return ai_owner_id
    return _owner_id_from_correction_text(source_text, sender_id=sender_id) or resolve_management_user_id(
        source_text,
        exclude_user_id=sender_id,
    )


def _normalize_direct_command(source_text: str) -> str:
    return re.sub(r"[\s。！？!?.，,]", "", source_text)


async def _handle_direct_draft_command(
    session: AsyncSession,
    message: DingTalkIncomingMessage,
    *,
    max_age_minutes: int,
) -> TDLCard | None:
    command = _normalize_direct_command(message.content)
    if command not in {"确认创建", "确认"} and not _looks_like_draft_cancel(message.content):
        return None
    latest_draft = await find_latest_recent_draft(
        session,
        created_by=message.sender_id,
        max_age_minutes=max_age_minutes,
    )
    if latest_draft is None:
        return None
    if _looks_like_draft_cancel(message.content):
        tdl = await cancel_draft_tdl(session, latest_draft.tdl_id, message.sender_id)
        return build_canceled_card(tdl)
    try:
        tdl = await confirm_tdl_with_calendar(session, latest_draft.tdl_id, message.sender_id)
    except ValueError:
        return build_draft_card(latest_draft)
    return build_created_card(tdl)


async def intake_dingtalk_message(
    session: AsyncSession,
    message: DingTalkIncomingMessage,
    ai_client: AIClient | None = None,
) -> TDLCard:
    client = ai_client or get_ai_client()
    follow_up_rules = _follow_up_rules()
    max_age_minutes = int(follow_up_rules.get("max_age_minutes", 15))
    direct_command_card = await _handle_direct_draft_command(
        session,
        message,
        max_age_minutes=max_age_minutes,
    )
    if direct_command_card is not None:
        return direct_command_card
    latest_draft = await find_latest_incomplete_draft(
        session,
        created_by=message.sender_id,
        max_age_minutes=max_age_minutes,
    )
    if _should_attempt_follow_up(
        latest_draft,
        source_text=message.content,
        sender_id=message.sender_id,
    ):
        is_correction = _looks_like_draft_correction(message.content)
        deterministic_owner_id = _owner_id_from_correction_text(
            message.content,
            sender_id=message.sender_id,
        )
        try:
            follow_up = await client.extract_tdl_follow_up(
                draft_title=latest_draft.title,
                source_text=message.content,
            )
        except TDLExtractionError:
            follow_up = None
        has_confident_ai_follow_up = (
            follow_up is not None
            and follow_up.is_follow_up
            and follow_up.confidence
            >= float(follow_up_rules.get("minimum_confidence", 0.80))
        )
        if deterministic_owner_id is not None or has_confident_ai_follow_up:
            updates = _build_follow_up_updates(
                latest_draft,
                source_text=message.content,
                sender_id=message.sender_id,
                deterministic_owner_id=deterministic_owner_id,
                follow_up=follow_up,
                has_confident_ai_follow_up=has_confident_ai_follow_up,
                is_correction=is_correction,
            )
            if updates.model_dump(exclude_none=True):
                tdl = await update_draft_tdl(
                    session,
                    latest_draft.tdl_id,
                    updates,
                    message.sender_id,
                )
                return build_draft_card(tdl)

    if _looks_like_draft_correction(message.content):
        latest_open_tdl = await find_latest_recent_open_tdl(
            session,
            created_by=message.sender_id,
            max_age_minutes=max_age_minutes,
        )
        if latest_open_tdl is not None:
            deterministic_owner_id = _owner_id_from_correction_text(
                message.content,
                sender_id=message.sender_id,
            )
            try:
                follow_up = await client.extract_tdl_follow_up(
                    draft_title=latest_open_tdl.title,
                    source_text=message.content,
                )
            except TDLExtractionError:
                follow_up = None
            has_confident_ai_follow_up = (
                follow_up is not None
                and follow_up.is_follow_up
                and follow_up.confidence
                >= float(follow_up_rules.get("minimum_confidence", 0.80))
            )
            if deterministic_owner_id is not None or has_confident_ai_follow_up:
                updates = _build_follow_up_updates(
                    latest_open_tdl,
                    source_text=message.content,
                    sender_id=message.sender_id,
                    deterministic_owner_id=deterministic_owner_id,
                    follow_up=follow_up,
                    has_confident_ai_follow_up=has_confident_ai_follow_up,
                    is_correction=True,
                )
                if updates.model_dump(exclude_none=True):
                    tdl = await update_open_tdl_from_follow_up(
                        session,
                        latest_open_tdl.tdl_id,
                        updates,
                        message.sender_id,
                    )
                    if updates.due_at is not None or updates.owner_id is not None:
                        tdl = await sync_calendar_due_at_change_best_effort(
                            session,
                            tdl,
                            actor_id=message.sender_id,
                        )
                    return build_created_card(tdl)
        if _looks_like_contextual_follow_up(message.content):
            return build_no_follow_up_target_card()

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
    extracted = replace(
        extracted,
        due_at=_normalize_date_only_due_at(
            extracted.due_at,
            source_text=message.content,
        ),
    )
    extracted = _normalize_unsupported_p0(extracted, source_text=message.content)
    resolved_owner_id = resolve_management_user_id(extracted.owner_id)
    mentioned_other_ids = _mentioned_other_management_ids(
        message.content,
        sender_id=message.sender_id,
    )
    inferred_owner_id = _infer_assigned_owner_id(
        message.content,
        sender_id=message.sender_id,
    )
    owner_id = resolved_owner_id or extracted.owner_id or inferred_owner_id or message.sender_id
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
