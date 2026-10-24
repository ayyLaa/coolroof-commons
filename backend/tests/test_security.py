import pytest

from app.core.exceptions import AuthenticationError, SecurityConfigurationError
from app.core.security import require_api_key


def test_local_mode_allows_unconfigured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MODE", "local")
    monkeypatch.delenv("WRITE_API_KEY", raising=False)
    require_api_key(None, "WRITE_API_KEY")


def test_remote_mode_fails_closed_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.delenv("WRITE_API_KEY", raising=False)
    with pytest.raises(SecurityConfigurationError):
        require_api_key(None, "WRITE_API_KEY")


def test_configured_key_is_always_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRITE_API_KEY", "operator-secret")
    with pytest.raises(AuthenticationError):
        require_api_key("wrong", "WRITE_API_KEY")
    require_api_key("operator-secret", "WRITE_API_KEY")


def test_event_key_is_separate_from_operator_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRITE_API_KEY", "operator-secret")
    monkeypatch.setenv("EVENT_API_KEY", "event-secret")
    with pytest.raises(AuthenticationError):
        require_api_key("operator-secret", "EVENT_API_KEY")
    require_api_key("event-secret", "EVENT_API_KEY")
