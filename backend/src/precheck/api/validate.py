"""Stateless validation helpers for authoring UIs (no persistence)."""

from fastapi import APIRouter
from pydantic import BaseModel

from precheck.schema import CheckRequest, RuleBody, content_hash, live_problems

router = APIRouter(prefix="/api/validate", tags=["validate"])


class RuleBodyValidation(BaseModel):
    content_hash: str
    jev_model: str | None
    live_problems: list[str]


@router.post("/rule-body", response_model=RuleBodyValidation)
def validate_rule_body(body: RuleBody) -> RuleBodyValidation:
    """422 if the body is invalid; otherwise its hash and anything blocking publication."""
    return RuleBodyValidation(
        content_hash=content_hash(body),
        jev_model=body.jev.model if body.jev else None,
        live_problems=live_problems(body),
    )


@router.post("/check-request", response_model=CheckRequest)
def validate_check_request(check_request: CheckRequest) -> CheckRequest:
    """422 if invalid; otherwise the normalized request."""
    return check_request
