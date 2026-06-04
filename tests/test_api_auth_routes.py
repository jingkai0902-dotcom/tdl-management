from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.auth import require_internal_api_key
from app.main import app


PROTECTED_PREFIXES = (
    "/tdls",
    "/dingtalk",
    "/meetings",
    "/reminders",
    "/reports",
)


def _route_for(path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            return route
    raise AssertionError(f"Route not registered: {path}")


def _dependency_calls(route: APIRoute) -> set:
    return {dependency.call for dependency in route.dependant.dependencies}


def test_internal_api_key_dependency_is_attached_to_internal_api_routes() -> None:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith(PROTECTED_PREFIXES):
            assert require_internal_api_key in _dependency_calls(route), route.path


def test_public_entry_routes_do_not_require_internal_api_key() -> None:
    for path in ("/", "/entry", "/health", "/calendar/auth/start", "/calendar/auth/callback"):
        route = _route_for(path)
        assert require_internal_api_key not in _dependency_calls(route), path


def test_protected_route_rejects_missing_key_in_production(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.auth.get_settings",
        lambda: type("Settings", (), {"app_env": "production", "internal_api_key": "secret"})(),
    )
    client = TestClient(app)

    response = client.get("/tdls")

    assert response.status_code == 401
