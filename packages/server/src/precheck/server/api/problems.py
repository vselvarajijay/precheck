"""RFC 7807 problem+json error responses."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from precheck.server.authoring.errors import LiveValidationError, ServiceError

PROBLEM_JSON = "application/problem+json"


class FieldError(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    errors: list[FieldError] | None = None


def problem(
    status: int, title: str, detail: str | None = None, errors: list[FieldError] | None = None
) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail, errors=errors)
    return JSONResponse(
        body.model_dump(exclude_none=True), status_code=status, media_type=PROBLEM_JSON
    )


def _loc(loc: tuple[Any, ...]) -> str:
    """Field path without FastAPI's leading `body` marker (`body.body.jev` -> `body.jev`)."""
    parts = list(loc[1:] if loc and loc[0] == "body" else loc)
    return ".".join(str(p) for p in parts) or "body"


def install(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service(_: Request, exc: ServiceError) -> JSONResponse:
        errors = None
        if isinstance(exc, LiveValidationError) and exc.problems:
            errors = [FieldError(field=p.field, message=p.message) for p in exc.problems]
        return problem(exc.status, exc.title, str(exc), errors)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [FieldError(field=_loc(tuple(e["loc"])), message=e["msg"]) for e in exc.errors()]
        return problem(422, "Invalid request", f"{len(errors)} validation error(s)", errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(exc.status_code, str(exc.detail))


# Documented on routes so the generated client knows the error shape.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": Problem, "description": "Not found"},
    409: {"model": Problem, "description": "Conflict"},
    422: {"model": Problem, "description": "Validation problem"},
}
