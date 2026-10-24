"""Locale normalization for Vietnamese receipts/invoices, policy `vi-VND.v1` (AI-2).

Raw source text → canonical business strings (business.schema.json):
money/quantity decimal strings without exponent or trailing fractional zeros,
date YYYY-MM-DD, time HH:MM[:SS], text NFC with collapsed whitespace.

Refusal is explicit: `absent` (nothing written), `ambiguous` (several readings),
`invalid` (not a value of that kind). Both refusals return value None so callers
emit an issue; nothing is guessed, rounded or inferred from other fields.
Shared by the rule baseline, model adapters and the evaluator; change → new version.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

POLICY_VERSION = "vi-VND.v1"
MAX_DECIMAL_LENGTH = 32  # business.schema.json NullableDecimal maxLength
MAX_TEXT_LENGTH = 500  # business.schema.json NullableText maxLength

Status = Literal["ok", "absent", "ambiguous", "invalid"]


@dataclass(frozen=True)
class Normalized:
    value: str | None
    raw: str | None
    status: Status
    reason: str | None = None


def _ok(raw: str | None, value: str) -> Normalized:
    return Normalized(value, raw, "ok")


def _refuse(raw: str | None, status: Status, reason: str) -> Normalized:
    return Normalized(None, raw, status, reason)


def _clean(raw: str | None) -> str:
    return " ".join(unicodedata.normalize("NFC", raw or "").split())


_CURRENCY = re.compile(r"^(?:vn[dđ]\s*)?(.*?)(?:\s*(?:vn[dđ]|đ|₫))?$", re.IGNORECASE)
_GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")


def _canonical(number: Decimal) -> str:
    text = format(number.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _decimal(raw: str | None, kind: Literal["money", "quantity"]) -> Normalized:
    text = _clean(raw)
    if not text:
        return _refuse(raw, "absent", "empty")
    if kind == "money":
        text = _CURRENCY.match(text).group(1)
    text = re.sub(r"(?<=\d) (?=\d{3}\b)", "", text)  # "45 000"
    if text.startswith("-"):
        return _refuse(raw, "invalid", "negative values are not supported")
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", text):
        return _refuse(raw, "invalid", "not a number")

    separators = set(re.findall(r"[.,]", text))
    if len(separators) == 2:
        decimal_sep = text[max(text.rfind("."), text.rfind(","))]
        integer, _, fraction = text.rpartition(decimal_sep)
        if decimal_sep in integer or not _GROUPED.match(integer):
            return _refuse(raw, "invalid", "inconsistent separators")
        digits = integer.replace("." if decimal_sep == "," else ",", "") + "." + fraction
    elif len(separators) == 1:
        sep = separators.pop()
        groups = text.split(sep)
        if len(groups) > 2:
            if not _GROUPED.match(text):
                return _refuse(raw, "invalid", "thousands groups must have 3 digits")
            digits = text.replace(sep, "")
        elif len(groups[1]) == 3 and len(groups[0]) <= 3 and groups[0] != "0":
            if kind == "quantity":
                return _refuse(raw, "ambiguous", "thousands separator or decimal fraction")
            digits = text.replace(sep, "")  # VND amounts have no 3-digit fractions
        else:
            digits = text.replace(sep, ".")
    else:
        digits = text

    try:
        value = _canonical(Decimal(digits))
    except InvalidOperation:
        return _refuse(raw, "invalid", "not a number")
    if len(value) > MAX_DECIMAL_LENGTH:
        return _refuse(raw, "invalid", "too many digits")
    return _ok(raw, value)


def normalize_money(raw: str | None) -> Normalized:
    """VND amount: `.`/`,`/space thousands, optional đ/₫/VND/VNĐ marker."""
    return _decimal(raw, "money")


def normalize_quantity(raw: str | None) -> Normalized:
    """Quantity: `1,5` → `1.5`; a lone 3-digit group (`2.000`) stays ambiguous."""
    return _decimal(raw, "quantity")


def normalize_number_literal(raw: str | None) -> Normalized:
    """Machine number literal (e.g. JSON `45000.10`): exact Decimal, no locale rules."""
    text = (raw or "").strip()
    if not text:
        return _refuse(raw, "absent", "empty")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
        return _refuse(raw, "invalid", "not a number literal")
    number = Decimal(text)
    if number < 0:
        return _refuse(raw, "invalid", "negative values are not supported")
    value = _canonical(number)
    if len(value) > MAX_DECIMAL_LENGTH:
        return _refuse(raw, "invalid", "too many digits")
    return _ok(raw, value)


_DATE_LABEL =re.compile(r"^(?:ngày|date)\s*:?\s*", re.IGNORECASE)
_DAY_FIRST = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_WORDS = re.compile(r"^(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})$", re.IGNORECASE)


def normalize_date(raw: str | None) -> Normalized:
    """Day-first Vietnamese dates or ISO; month-first is never assumed."""
    text = _clean(raw)
    if not text:
        return _refuse(raw, "absent", "empty")
    text = _DATE_LABEL.sub("", text)
    if match := _ISO.match(text):
        year, month, day = match.groups()
    elif match := _DAY_FIRST.match(text) or _WORDS.match(text):
        day, month, year = match.groups()
        if len(year) == 2:
            return _refuse(raw, "ambiguous", "two-digit year")
    else:
        return _refuse(raw, "invalid", "unrecognized date format")
    try:
        return _ok(raw, date(int(year), int(month), int(day)).isoformat())
    except ValueError:
        return _refuse(raw, "invalid", "date does not exist")


_TIME_LABEL = re.compile(r"^(?:giờ|time)\s*:?\s*", re.IGNORECASE)
_TIME = re.compile(
    r"^(\d{1,2})(?::(\d{2})(?::(\d{2}))?|[hHgG](\d{2})?)\s*(am|pm|sa|ch)?$",
    re.IGNORECASE,
)


def normalize_time(raw: str | None) -> Normalized:
    """`14:30`, `14h30`, `2:30 PM`/`CH` (chiều), `SA` (sáng) → HH:MM[:SS]."""
    text = _clean(raw)
    if not text:
        return _refuse(raw, "absent", "empty")
    match = _TIME.match(_TIME_LABEL.sub("", text))
    if not match:
        return _refuse(raw, "invalid", "unrecognized time format")
    hour_text, colon_minute, second, h_minute, meridiem = match.groups()
    hour, minute = int(hour_text), int(colon_minute or h_minute or 0)
    if meridiem:
        if not 1 <= hour <= 12:
            return _refuse(raw, "invalid", "12-hour clock out of range")
        afternoon = meridiem.lower() in ("pm", "ch")
        hour = hour % 12 + (12 if afternoon else 0)
    if hour > 23 or minute > 59 or (second is not None and int(second) > 59):
        return _refuse(raw, "invalid", "time does not exist")
    value = f"{hour:02d}:{minute:02d}" + (f":{int(second):02d}" if second is not None else "")
    return _ok(raw, value)


def normalize_text(raw: str | None) -> Normalized:
    """NFC, trimmed, internal whitespace collapsed; Vietnamese marks are kept."""
    text = _clean(raw)
    if not text:
        return _refuse(raw, "absent", "empty")
    if len(text) > MAX_TEXT_LENGTH:
        return _refuse(raw, "invalid", "longer than schema limit")
    return _ok(raw, text)
