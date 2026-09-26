"""Content hashes: sha256 over canonical JSON (sorted keys, no whitespace, UTF-8)."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json(value: BaseModel | Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: BaseModel | Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
