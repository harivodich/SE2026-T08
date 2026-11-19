"""Bounded JSON/UTF-8 output policy before schema traversal or HTTP publication."""

from __future__ import annotations

import json
import math
from typing import Any

MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_DEPTH = 32


def _members(value: dict):
    for key, item in value.items():
        if type(key) is not str:
            raise ValueError("Output object keys must be strings")
        yield key
        yield item


def encode_output(value: Any) -> bytes:
    """Reject unsafe Python objects and bound work before validating the schema.

    Iterators bound traversal memory by depth, including for wide containers.
    A lower byte bound bounds traversal work; encoded bytes enforce the exact cap.
    Cycles exceed the depth cap without recursing or changing recursion limits.
    """
    stack = [(iter((value,)), 0)]
    minimum_bytes = 0
    while stack:
        iterator, depth = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        kind = type(item)
        minimum_bytes += 1
        if kind is str:
            if len(item) > MAX_OUTPUT_BYTES:
                raise ValueError("Output exceeds byte limit")
            minimum_bytes += len(item.encode("utf-8", errors="strict")) + 1
        elif kind in (dict, list):
            if depth >= MAX_OUTPUT_DEPTH:
                raise ValueError("Output exceeds depth limit")
            stack.append((iter(_members(item) if kind is dict else item), depth + 1))
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError("Output numbers must be finite")
        elif kind not in (int, bool, type(None)):
            raise ValueError("Output contains a non-JSON type")
        if minimum_bytes > MAX_OUTPUT_BYTES:
            raise ValueError("Output exceeds byte limit")

    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    body = bytearray()
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode("utf-8", errors="strict")
        if len(body) + len(encoded) > MAX_OUTPUT_BYTES:
            raise ValueError("Output exceeds byte limit")
        body.extend(encoded)
    return bytes(body)
