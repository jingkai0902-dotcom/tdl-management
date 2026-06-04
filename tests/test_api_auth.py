from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.auth import require_internal_api_key


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({"type": "http", "headers": headers or []})


def test_internal_api_key_allows_development_without_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.auth.get_settings",
        lambda: SimpleNamespace(app_env="development", internal_api_key=""),
    )

    require_internal_api_key(_request())


def test_internal_api_key_rejects_production_without_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.auth.get_settings",
        lambda: SimpleNamespace(app_env="production", internal_api_key=""),
    )

    with pytest.raises(HTTPException) as exc_info:
        require_internal_api_key(_request())

    assert exc_info.value.status_code == 503


def test_internal_api_key_requires_header_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.auth.get_settings",
        lambda: SimpleNamespace(app_env="production", internal_api_key="secret"),
    )

    with pytest.raises(HTTPException) as exc_info:
        require_internal_api_key(_request())

    assert exc_info.value.status_code == 401


def test_internal_api_key_rejects_wrong_header(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.auth.get_settings",
        lambda: SimpleNamespace(app_env="production", internal_api_key="secret"),
    )

    with pytest.raises(HTTPException) as exc_info:
        require_internal_api_key(_request([(b"x-tdl-internal-key", b"wrong")]))

    assert exc_info.value.status_code == 403


def test_internal_api_key_accepts_correct_header(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.auth.get_settings",
        lambda: SimpleNamespace(app_env="production", internal_api_key="secret"),
    )

    require_internal_api_key(_request([(b"x-tdl-internal-key", b"secret")]))
