"""Stateless validation helpers for authoring UIs (no persistence).

`/rule-body` always answers 200 with `valid` + field errors, so editors can validate on
every keystroke without error responses; the create/update endpoints still return 422.
"""

from typing import Any

from fastapi import APIRouter, Body
from pydantic import BaseModel, ValidationError

from precheck.api.problems import FieldError
from precheck.schema import CheckRequest, RuleBody, content_hash, live_problems

router = APIRouter(prefix="/api/validate", tags=["validate"])


class RuleBodyValidation(BaseModel):
    valid: bool
    errors: list[FieldError]
    content_hash: str | None = None
    jev_model: str | None = None
    live_problems: list[str] = []


@router.post("/rule-body", response_model=RuleBodyValidation)
def validate_rule_body(body: dict[str, Any] = Body(...)) -> RuleBodyValidation:  # noqa: B008
    """Validate a candidate RuleBody; `live_problems` lists what blocks publication."""
    try:
        parsed = RuleBody.model_validate(body)
    except ValidationError as e:
        errors = [
            FieldError(field=".".join(str(p) for p in err["loc"]) or "body", message=err["msg"])
            for err in e.errors()
        ]
        return RuleBodyValidation(valid=False, errors=errors)
    return RuleBodyValidation(
        valid=True,
        errors=[],
        content_hash=content_hash(parsed),
        jev_model=parsed.jev.model if parsed.jev else None,
        live_problems=live_problems(parsed),
    )


@router.post("/check-request", response_model=CheckRequest)
def validate_check_request(check_request: CheckRequest) -> CheckRequest:
    """422 if invalid; otherwise the normalized request."""
    return check_request
