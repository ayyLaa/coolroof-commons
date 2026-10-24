from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class CoolRoofError(Exception):
    """Base class: each subclass carries the HTTP status and error code the router
    layer translates it to, so services never deal with HTTP themselves."""

    status_code = 500
    code = "internal_error"


class RoofNotFoundError(CoolRoofError):
    status_code = 404
    code = "not_found"

    def __init__(self, roof_id: str) -> None:
        self.roof_id = roof_id
        super().__init__(f"No record found for {roof_id}.")


class MeasurementNotFoundError(CoolRoofError):
    status_code = 404
    code = "not_found"

    def __init__(self, measurement_id: str) -> None:
        self.measurement_id = measurement_id
        super().__init__(f"No measurement found for {measurement_id}.")


class MissingMeasurementError(CoolRoofError):
    status_code = 409
    code = "missing_measurement"

    def __init__(self, roof_id: str, phase: str) -> None:
        super().__init__(f"{roof_id} has no '{phase}' measurement yet.")


class WeatherUnavailableError(CoolRoofError):
    status_code = 503
    code = "weather_unavailable"


class AuthenticationError(CoolRoofError):
    status_code = 401
    code = "unauthorized"


class SecurityConfigurationError(CoolRoofError):
    status_code = 503
    code = "security_unavailable"


class InvalidChainEventError(CoolRoofError):
    status_code = 422
    code = "invalid_chain_event"


class SigningUnavailableError(CoolRoofError):
    status_code = 503
    code = "signing_unavailable"


class InvalidPhotoError(CoolRoofError):
    status_code = 422
    code = "invalid_photo"


class ArtifactNotGeneratedError(CoolRoofError):
    status_code = 404
    code = "not_generated"


class TimezoneError(CoolRoofError):
    status_code = 422
    code = "timezone_error"


class StaleRoundError(CoolRoofError):
    """An escrow event from another demo round: applying it would overwrite the current
    round's tranche states with a different project's."""

    status_code = 409
    code = "stale_round"

    def __init__(self, event_round: int, current_round: int) -> None:
        super().__init__(
            f"Event is from demo round {event_round}; the backend mirrors round {current_round}."
        )


class SnapshotFormatError(CoolRoofError):
    """A data/snapshots CSV row that cannot be loaded back into the database."""

    status_code = 422
    code = "invalid_snapshot"


class MixedDataSourceError(CoolRoofError):
    """Raised instead of comparing a measured value with a simulated one."""

    status_code = 409
    code = "mixed_data_source"


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CoolRoofError)
    async def _handle_domain_error(_: Request, exc: CoolRoofError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {"loc": (), "msg": "Invalid request."}
        location = ".".join(str(part) for part in first["loc"])
        return _error_response(422, "validation_error", f"{location}: {first['msg']}")
