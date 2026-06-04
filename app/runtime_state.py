from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import BASE_DIR, get_settings


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
STATE_SCHEMA_VERSION = 1
MAX_ERROR_SUMMARY_CHARS = 500
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|api[_-]?key|password|secret)\b"
    r"(\s*[=:]\s*)"
    r"([^\s,;}\]]+)"
)
AUTHORIZATION_BEARER_PATTERN = re.compile(
    r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s,;}\]]+)"
)
SAFE_PROCESS_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def default_runtime_state_dir() -> Path:
    settings = get_settings()
    if settings.runtime_state_dir:
        return Path(settings.runtime_state_dir)
    return BASE_DIR / "runtime_state"


def runtime_state_path(process_name: str, *, state_dir: Path | str | None = None) -> Path:
    safe_name = _safe_process_name(process_name)
    resolved_dir = Path(state_dir) if state_dir is not None else default_runtime_state_dir()
    return resolved_dir / f"{safe_name}.state.json"


def write_heartbeat(
    process_name: str,
    *,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
    pid: int | None = None,
    best_effort: bool = True,
) -> bool:
    timestamp = _timestamp(now)
    return _update_state(
        process_name,
        {
            "last_heartbeat_at": timestamp,
            "current_mode": "healthy",
            "stop_signal": None,
        },
        state_dir=state_dir,
        now=now,
        pid=pid,
        best_effort=best_effort,
    )


def write_started(
    process_name: str,
    *,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
    pid: int | None = None,
    best_effort: bool = True,
) -> bool:
    return _update_state(
        process_name,
        {
            "last_started_at": _timestamp(now),
            "current_mode": "healthy",
            "stop_signal": None,
        },
        state_dir=state_dir,
        now=now,
        pid=pid,
        best_effort=best_effort,
    )


def write_success(
    process_name: str,
    *,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
    pid: int | None = None,
    processed_increment: int = 1,
    best_effort: bool = True,
) -> bool:
    return _update_state(
        process_name,
        {
            "last_success_at": _timestamp(now),
            "last_error": None,
            "current_mode": "healthy",
            "stop_signal": None,
            "_processed_increment": processed_increment,
        },
        state_dir=state_dir,
        now=now,
        pid=pid,
        best_effort=best_effort,
    )


def write_failure(
    process_name: str,
    error: Exception | str,
    *,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
    pid: int | None = None,
    current_mode: str = "degraded",
    stop_signal: str | None = None,
    best_effort: bool = True,
) -> bool:
    return _update_state(
        process_name,
        {
            "last_error_at": _timestamp(now),
            "last_error": summarize_error(error),
            "current_mode": current_mode,
            "stop_signal": stop_signal,
        },
        state_dir=state_dir,
        now=now,
        pid=pid,
        best_effort=best_effort,
    )


def summarize_error(error: Exception | str, *, limit: int = MAX_ERROR_SUMMARY_CHARS) -> str:
    if isinstance(error, Exception):
        raw = f"{type(error).__name__}: {error}"
    else:
        raw = str(error)
    compact = " ".join(raw.split())
    redacted = SECRET_VALUE_PATTERN.sub(r"\1\2[REDACTED]", compact)
    redacted = AUTHORIZATION_BEARER_PATTERN.sub(r"\1[REDACTED]", redacted)
    if len(redacted) <= limit:
        return redacted
    return f"{redacted[: max(0, limit - 3)]}..."


def _update_state(
    process_name: str,
    updates: dict,
    *,
    state_dir: Path | str | None,
    now: datetime | None,
    pid: int | None,
    best_effort: bool,
) -> bool:
    try:
        path = runtime_state_path(process_name, state_dir=state_dir)
        existing = _read_state(path)
        processed_increment = int(updates.pop("_processed_increment", 0) or 0)
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "process_name": process_name,
            "pid": pid if pid is not None else os.getpid(),
            "started_at": existing.get("started_at") or _timestamp(now),
            "last_heartbeat_at": existing.get("last_heartbeat_at"),
            "last_started_at": existing.get("last_started_at"),
            "last_success_at": existing.get("last_success_at"),
            "last_error_at": existing.get("last_error_at"),
            "last_error": existing.get("last_error"),
            "processed_count": int(existing.get("processed_count") or 0) + processed_increment,
            "current_mode": existing.get("current_mode") or "healthy",
            "stop_signal": existing.get("stop_signal"),
        }
        state.update(updates)
        _atomic_write_json(path, state)
        return True
    except Exception:
        if best_effort:
            return False
        raise


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _safe_process_name(process_name: str) -> str:
    normalized = SAFE_PROCESS_NAME_PATTERN.sub("_", process_name.strip())
    normalized = normalized.strip("._-")
    if not normalized:
        raise ValueError("process_name must contain at least one safe character")
    return normalized


def _timestamp(value: datetime | None = None) -> str:
    resolved = value or datetime.now(tz=SHANGHAI_TZ)
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=SHANGHAI_TZ)
    return resolved.isoformat()
