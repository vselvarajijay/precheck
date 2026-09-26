"""Read the proxy's reply the way an agent sees it: what happened to the call and result."""

import json
import re

from mcp.types import CallToolResult, TextContent

from precheck.core.schema import Verdict

_WITHHELD = re.compile(r"withheld by precheck \((deny|escalate)\)")


def reply_text(result: CallToolResult) -> str:
    texts = [c.text for c in result.content if isinstance(c, TextContent)]
    if texts:
        return "\n".join(texts)
    return json.dumps(result.structured_content) if result.structured_content is not None else ""


def classify(result: CallToolResult) -> tuple[Verdict, Verdict | None]:
    """(verdict on the call, verdict on the result or None if the result wasn't judged)."""
    text = reply_text(result)
    if not result.is_error:
        return Verdict.allow, Verdict.allow
    if text.startswith("Blocked by precheck"):
        return Verdict.deny, None
    if text.startswith("Held for human approval"):
        return Verdict.escalate, None
    if m := _WITHHELD.search(text):
        return Verdict.allow, Verdict(m.group(1))
    return Verdict.allow, None  # the tool itself failed (e.g. order not found)
