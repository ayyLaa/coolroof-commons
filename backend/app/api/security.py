from typing import Annotated

from fastapi import Header

from app.core.security import require_api_key

ApiKey = Annotated[str | None, Header(alias="X-API-Key")]


def require_operator(api_key: ApiKey = None) -> None:
    require_api_key(api_key, "WRITE_API_KEY")


def require_oracle(api_key: ApiKey = None) -> None:
    require_api_key(api_key, "EVENT_API_KEY")
