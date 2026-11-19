"""Bounded decoding for private compute metadata, independent of schema validity."""

from __future__ import annotations

import json
from typing import Any

MAX_METADATA_DEPTH = 8  # count object/array containers; compute v1 is a flat object


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metadata key")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("non-finite metadata number")


def decode_metadata(text: str) -> Any:
    """Reject excessive nesting before json.loads can exhaust the Python stack."""
    depth = 0
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_METADATA_DEPTH:
                raise ValueError("metadata nesting too deep")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced metadata")
    try:
        return json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except RecursionError as error:
        raise ValueError("metadata decoder limit exceeded") from error
