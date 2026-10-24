import os
from hmac import compare_digest

from app.core.exceptions import AuthenticationError, SecurityConfigurationError


def require_api_key(provided: str | None, environment_name: str) -> None:
    expected = os.getenv(environment_name, "")
    if not expected:
        if os.getenv("APP_MODE", "local") == "local":
            return
        raise SecurityConfigurationError(f"{environment_name} must be configured outside local mode.")
    if not provided or not compare_digest(provided.encode(), expected.encode()):
        raise AuthenticationError("A valid API key is required for this operation.")
