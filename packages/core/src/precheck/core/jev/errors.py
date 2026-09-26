"""Typed Jev failures. The engine maps any of these to a rule's `on_error` verdict."""


class JevError(Exception):
    """Base class for every Jev client failure."""


class JevAuthError(JevError):
    """401/403: bad or missing API key. Never retried."""


class JevValidationError(JevError):
    """400/422: Jev rejected the request. Never retried; `body` holds Jev's explanation."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Jev rejected the request (HTTP {status}): {body[:500]}")
        self.status = status
        self.body = body


class JevTimeout(JevError):
    """The overall deadline passed (including retries)."""


class JevUnavailable(JevError):
    """429/529/5xx or transport errors persisted after retries."""


class JevRequestTooLarge(JevError):
    """State plus a single question exceeds Jev's token limits; we never silently truncate."""


class JevFixtureMissing(JevError):
    """Replay mode found no recorded response for this request."""

    def __init__(self, request_hash: str, path: str) -> None:
        super().__init__(
            f"no recorded Jev fixture for request {request_hash} (expected {path}); "
            "re-record with JEV_MODE=record"
        )
        self.request_hash = request_hash
