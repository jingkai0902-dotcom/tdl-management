from app.services.intake_service import _fallback_due_at


def test_fallback_due_at_is_timezone_aware() -> None:
    assert _fallback_due_at().tzinfo is not None
