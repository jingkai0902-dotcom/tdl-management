from __future__ import annotations

from difflib import SequenceMatcher
import re

from app.config import load_yaml_config


_HOMOPHONE_EQUIVALENTS = {
    "珍": {"真", "祯", "贞", "甄"},
    "颖": {"影", "颍", "莹", "瑛", "英"},
    "皓": {"浩", "昊", "灏"},
    "蕾": {"雷", "磊"},
    "冉": {"然"},
    "楠": {"南"},
    "肖": {"潇", "萧"},
    "晓": {"小"},
    "华": {"花"},
    "艳": {"燕", "彦"},
    "明": {"鸣"},
    "敏": {"闵"},
    "邢": {"刑", "行"},
    "杨": {"阳", "洋"},
}

_FUZZY_MATCH_REVIEWED_NAMES = {
    "李珍",
    "张蕾",
    "荆少巍",
    "张皓",
    "许梦冉",
    "时颖",
    "苗雅楠",
    "李肖",
    "赵晓华",
    "曹艳明",
    "韩雪敏",
    "邢杨",
}


def _management_roster() -> list[dict]:
    return load_yaml_config("management_roster.yaml").get("management", [])


def management_aliases_by_user_id() -> dict[str, set[str]]:
    aliases_by_user_id: dict[str, set[str]] = {}
    for member in _management_roster():
        user_id = member.get("dingtalk_user_id")
        if not user_id:
            continue
        aliases = {
            str(value).strip()
            for key in ("name", "english_name")
            if (value := member.get(key))
        }
        if aliases:
            aliases_by_user_id[str(user_id)] = aliases
    return aliases_by_user_id


def _management_spoken_aliases_by_user_id() -> dict[str, set[str]]:
    aliases_by_user_id: dict[str, set[str]] = {}
    for member in _management_roster():
        user_id = member.get("dingtalk_user_id")
        if not user_id:
            continue
        aliases = {str(alias).strip() for alias in member.get("spoken_aliases", []) if alias}
        if aliases:
            aliases_by_user_id[str(user_id)] = aliases
    return aliases_by_user_id


def roster_name_to_user_id() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for user_id, aliases in management_aliases_by_user_id().items():
        for alias in aliases:
            mapping[alias] = user_id
    return mapping


def unreviewed_fuzzy_match_names() -> set[str]:
    """Names that were added to the roster without fuzzy-match review."""
    roster_names = {
        str(member["name"]).strip()
        for member in _management_roster()
        if member.get("name")
    }
    return roster_names - _FUZZY_MATCH_REVIEWED_NAMES


def format_management_name(user_id: str | None) -> str | None:
    if user_id is None:
        return None
    for member in _management_roster():
        if str(member.get("dingtalk_user_id")) != user_id:
            continue
        name = member.get("name", "")
        english_name = member.get("english_name", "")
        return f"{name} / {english_name}" if name and english_name else (name or user_id)
    return None


def resolve_management_user_id(name_or_text: str | None, *, exclude_user_id: str | None = None) -> str | None:
    if not name_or_text:
        return None
    text = _normalize_match_text(name_or_text)
    exact_matches = [
        user_id
        for user_id, aliases in management_aliases_by_user_id().items()
        if user_id != exclude_user_id and any(_alias_matches_text(alias, name_or_text) for alias in aliases)
    ]
    if len(set(exact_matches)) == 1:
        return exact_matches[0]

    spoken_alias_match = _resolve_spoken_alias(name_or_text, exclude_user_id=exclude_user_id)
    if spoken_alias_match is not None:
        return spoken_alias_match

    english_match = _resolve_fuzzy_english_alias(text, exclude_user_id=exclude_user_id)
    if english_match is not None:
        return english_match

    fuzzy_matches = []
    for user_id, aliases in management_aliases_by_user_id().items():
        if user_id == exclude_user_id:
            continue
        for alias in aliases:
            if _is_english_alias(alias):
                continue
            score = _best_alias_score(text, _normalize_match_text(alias))
            if score >= 0.92:
                fuzzy_matches.append((score, user_id))
                break
    if not fuzzy_matches:
        return None
    fuzzy_matches.sort(reverse=True)
    best_score = fuzzy_matches[0][0]
    best_user_ids = {user_id for score, user_id in fuzzy_matches if score == best_score}
    if len(best_user_ids) == 1:
        return best_user_ids.pop()
    return None


def _resolve_spoken_alias(text: str, *, exclude_user_id: str | None = None) -> str | None:
    if not _has_owner_context(text):
        return None
    matches = [
        user_id
        for user_id, aliases in _management_spoken_aliases_by_user_id().items()
        if user_id != exclude_user_id and any(_alias_matches_text(alias, text) for alias in aliases)
    ]
    if len(set(matches)) == 1:
        return matches[0]
    return None


def _resolve_fuzzy_english_alias(text: str, *, exclude_user_id: str | None = None) -> str | None:
    tokens = re.findall(r"[a-z]{3,}", text)
    if not tokens:
        return None
    fuzzy_matches = []
    for user_id, aliases in management_aliases_by_user_id().items():
        if user_id == exclude_user_id:
            continue
        english_aliases = [
            _normalize_match_text(alias)
            for alias in aliases
            if _is_english_alias(alias)
        ]
        for token in tokens:
            for alias in english_aliases:
                score = SequenceMatcher(None, token, alias).ratio()
                if score >= 0.84:
                    fuzzy_matches.append((score, user_id))
                    break
    if not fuzzy_matches:
        return None
    fuzzy_matches.sort(reverse=True)
    best_score = fuzzy_matches[0][0]
    best_user_ids = {user_id for score, user_id in fuzzy_matches if score == best_score}
    if len(best_user_ids) == 1:
        return best_user_ids.pop()
    return None


def _alias_matches_text(alias: str, text: str) -> bool:
    if _is_english_alias(alias):
        return _normalize_match_text(alias) in re.findall(r"[a-z]+", text.lower())
    return _normalize_match_text(alias) in _normalize_match_text(text)


def _has_owner_context(text: str) -> bool:
    return any(
        keyword in text.lower()
        for keyword in (
            "负责人",
            "负责",
            "任务",
            "tdl",
            "owner",
            "请",
            "让",
            "由",
            "交给",
            "改成",
            "换成",
            "不是",
            "是",
            "提交",
            "跟进",
        )
    )


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[\s。！？!?.，,、；;：:\"'“”‘’（）()\[\]【】]", "", value).lower()


def _is_english_alias(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z\s._-]*", value.strip()))


def _best_alias_score(text: str, alias: str) -> float:
    if not text or not alias:
        return 0.0
    if alias in text:
        return 1.0
    if len(alias) == 1:
        return 0.0
    windows = (
        text[index : index + len(alias)]
        for index in range(0, max(len(text) - len(alias) + 1, 0))
    )
    return max((_alias_score(window, alias) for window in windows), default=0.0)


def _alias_score(candidate: str, alias: str) -> float:
    if len(candidate) != len(alias):
        return 0.0
    scores = []
    for got, expected in zip(candidate, alias):
        if got == expected:
            scores.append(1.0)
        elif got in _HOMOPHONE_EQUIVALENTS.get(expected, set()):
            scores.append(0.92)
        else:
            scores.append(SequenceMatcher(None, got, expected).ratio())
    return sum(scores) / len(scores)
