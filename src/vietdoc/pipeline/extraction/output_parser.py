"""Model raw output → business payload (M2.2), shared by baseline/model adapters.

No repair: the text must be one standalone JSON object, optionally inside a single
```json fence. Shape follows business.schema.json exactly (all keys, no extras,
≤30 rows); a broken shape is `schema_invalid`, not a payload of nulls. Present
values go through normalization `vi-VND.v2`; refusals become null + warning issue
and keep the raw text for field metadata. Numbers are never read as binary floats.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from vietdoc.contracts.compute import BUSINESS_SCHEMA, ComputeContracts, ContractError
from vietdoc.pipeline.normalization import (
    POLICY_VERSION,
    Normalized,
    normalize_date,
    normalize_money,
    normalize_number_literal,
    normalize_quantity,
    normalize_text,
    normalize_time,
)

MAX_RAW_CHARS = 64 * 1024
MAX_ITEMS = 30  # business.schema.json Items.maxItems
MAX_DEPTH = 8  # payload needs 3 (object → items → row); checked before json.loads

Status = Literal["ok", "no_json", "malformed_json", "truncated", "too_large", "schema_invalid"]

_FENCE = re.compile(r"^```(?:json)?[ \t]*\n(.*?)\n?```$", re.DOTALL | re.IGNORECASE)
_NORMALIZERS: dict[str, Callable[[str | None], Normalized]] = {
    "NullableText": normalize_text,
    "NullableDate": normalize_date,
    "NullableTime": normalize_time,
    "NullableDecimal": normalize_money,
}
_ISSUE_MESSAGES = {
    "ambiguous": "Giá trị đọc được có nhiều cách hiểu; để trống và cần đối chiếu nguồn.",
    "invalid": "Giá trị đọc được không hợp lệ cho trường này; để trống và cần đối chiếu nguồn.",
}


@dataclass(frozen=True)
class ParsedOutput:
    status: Status
    payload: dict[str, Any] | None
    raw_json_valid: bool  # strict parse succeeded before any normalization
    fenced: bool = False
    reason: str | None = None
    issues: tuple[dict[str, Any], ...] = ()
    raw_values: dict[str, str | None] = field(default_factory=dict)  # JSON Pointer → source text
    normalizer_version: str = POLICY_VERSION


class _NumberLiteral(str):
    """JSON number kept as its exact source text."""


class _ShapeError(ValueError):
    pass


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _too_deep(text: str) -> bool:
    depth, in_string, escaped = 0, False, False
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
            if depth > MAX_DEPTH:
                return True
        elif char in "]}":
            depth -= 1
    return False


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name}")


def _check_keys(obj: Any, expected: Mapping[str, str], where: str) -> None:
    if not isinstance(obj, dict):
        raise _ShapeError(f"{where or '/'} must be an object")
    missing, extra = expected.keys() - obj.keys(), obj.keys() - expected.keys()
    if missing or extra:
        raise _ShapeError(f"{where or '/'} keys differ: missing={sorted(missing)} extra={sorted(extra)}")


def _value(raw: Any, kind: str, key: str, path: str) -> Normalized:
    if raw is not None and not isinstance(raw, str):
        raise _ShapeError(f"{path} must be a string or null")
    if isinstance(raw, _NumberLiteral):
        if kind != "NullableDecimal":
            raise _ShapeError(f"{path} must be a string or null")
        return normalize_number_literal(str(raw))
    if kind == "NullableDecimal" and key == "quantity":
        return normalize_quantity(raw)
    return _NORMALIZERS[kind](raw)


def parse_model_output(
    raw: str,
    document_type: str,
    contracts: ComputeContracts,
    finish_reason: str | None = None,
) -> ParsedOutput:
    scalar_kinds, item_kinds = contracts.business_fields(document_type)
    if len(raw) > MAX_RAW_CHARS:
        return ParsedOutput("too_large", None, False, reason=f"output longer than {MAX_RAW_CHARS} chars")
    if finish_reason == "length":
        return ParsedOutput("truncated", None, False, reason="generation stopped at the token limit")

    text = raw.strip()
    fence = _FENCE.match(text)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith(("{", "[")):
        return ParsedOutput("no_json", None, False, fence is not None, "no standalone JSON value")
    if _too_deep(text):
        return ParsedOutput("malformed_json", None, False, fence is not None, "nesting too deep")
    try:
        data = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_int=_NumberLiteral,
            parse_float=_NumberLiteral,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError):
        return ParsedOutput("malformed_json", None, False, fence is not None, "invalid JSON")

    payload: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    raw_values: dict[str, str | None] = {}

    def take(value: Any, kind: str, key: str, path: str) -> str | None:
        result = _value(value, kind, key, path)
        raw_values[path] = None if value is None else str(value)
        if result.status in ("ambiguous", "invalid"):
            code = "VALUE_AMBIGUOUS" if result.status == "ambiguous" else "VALUE_INVALID"
            issues.append(
                {
                    "id": f"{code}:{path}",
                    "code": code,
                    "severity": "warning",
                    "paths": [path],
                    "message": _ISSUE_MESSAGES[result.status],
                }
            )
        return result.value

    try:
        _check_keys(data, {**scalar_kinds, "items": ""}, "")
        for key, kind in scalar_kinds.items():
            payload[key] = take(data[key], kind, key, f"/{key}")
        rows = data["items"]
        if not isinstance(rows, list):
            raise _ShapeError("/items must be an array")
        if len(rows) > MAX_ITEMS:
            raise _ShapeError(f"/items has {len(rows)} rows, limit {MAX_ITEMS}")
        payload["items"] = []
        for index, row in enumerate(rows):
            _check_keys(row, item_kinds, f"/items/{index}")
            payload["items"].append(
                {key: take(row[key], kind, key, f"/items/{index}/{key}") for key, kind in item_kinds.items()}
            )
        contracts.validate(BUSINESS_SCHEMA, payload)
    except (_ShapeError, ContractError) as error:
        return ParsedOutput("schema_invalid", None, True, fence is not None, str(error)[:500])

    return ParsedOutput("ok", payload, True, fence is not None, None, tuple(issues), raw_values)
