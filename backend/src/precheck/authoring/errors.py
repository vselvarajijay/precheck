"""Service-layer errors; the API maps them to RFC 7807 problem responses."""

from dataclasses import dataclass


class ServiceError(Exception):
    status = 400
    title = "Bad request"


class NotFoundError(ServiceError):
    status = 404
    title = "Not found"


class ConflictError(ServiceError):
    status = 409
    title = "Conflict"


@dataclass
class FieldProblem:
    field: str
    message: str


class LiveValidationError(ServiceError):
    """The rule cannot go live; `problems` name each offending field."""

    status = 422
    title = "Rule cannot be published"

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("; ".join(f"{p.field}: {p.message}" for p in problems))
        self.problems = problems
