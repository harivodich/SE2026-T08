"""Normalization policy vi-VND.v2: known raw → canonical values and refusal cases."""

from decimal import Inexact, InvalidOperation, Rounded, localcontext
import re

import pytest

from vietdoc.pipeline.normalization import (
    POLICY_VERSION,
    MAX_NUMBER_CHARS,
    normalize_date,
    normalize_money,
    normalize_number_literal,
    normalize_quantity,
    normalize_text,
    normalize_time,
)

DECIMAL = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")  # business.schema.json NullableDecimal


def test_policy_is_versioned():
    assert POLICY_VERSION == "vi-VND.v2"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("45.000", "45000"),
        ("15.000", "15000"),
        ("1.250.000", "1250000"),
        ("45,000", "45000"),
        ("1,250,000", "1250000"),
        ("45 000", "45000"),
        ("45000", "45000"),
        ("45.000đ", "45000"),
        ("45.000 ₫", "45000"),
        ("VND 45.000", "45000"),
        ("45.000 VNĐ", "45000"),
        ("1.250.000,50", "1250000.5"),
        ("1,250,000.50", "1250000.5"),
        ("12,5", "12.5"),
        ("45.00", "45"),
        ("0", "0"),
        ("000", "0"),
        ("  45.000  ", "45000"),
    ],
)
def test_money_canonical(raw, expected):
    result = normalize_money(raw)
    assert (result.status, result.value) == ("ok", expected)
    assert result.raw == raw
    assert DECIMAL.match(result.value)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_money_absent(raw):
    result = normalize_money(raw)
    assert (result.status, result.value) == ("absent", None)


@pytest.mark.parametrize(
    "raw",
    ["-5.000", "abc", "45.000.00", "1.25.000", "4,5.000", "45.000$", "1e5", "12..5", "1.250.000,50,1", "9" * 40],
)
def test_money_invalid(raw):
    result = normalize_money(raw)
    assert result.status == "invalid" and result.value is None and result.reason


@pytest.mark.parametrize(("raw", "expected"), [("3", "3"), ("1,5", "1.5"), ("0.25", "0.25"), ("2.000", None), ("10", "10")])
def test_quantity(raw, expected):
    result = normalize_quantity(raw)
    if expected is None:
        assert (result.status, result.value) == ("ambiguous", None)
    else:
        assert (result.status, result.value) == ("ok", expected)


def test_quantity_rejects_currency_symbol():
    assert normalize_quantity("3đ").status == "invalid"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("06/10/2026", "2026-10-06"),
        ("6/10/2026", "2026-10-06"),
        ("06-10-2026", "2026-10-06"),
        ("06.10.2026", "2026-10-06"),
        ("2026-10-06", "2026-10-06"),
        ("Ngày 06 tháng 10 năm 2026", "2026-10-06"),
        ("ngày 6 tháng 10 năm 2026", "2026-10-06"),
        ("Ngày: 06/10/2026", "2026-10-06"),
        ("29/02/2028", "2028-02-29"),
    ],
)
def test_date_canonical(raw, expected):
    assert (normalize_date(raw).status, normalize_date(raw).value) == ("ok", expected)


@pytest.mark.parametrize(("raw", "status"), [("06/10/26", "ambiguous"), ("31/02/2026", "invalid"), ("29/02/2026", "invalid"), ("13/13/2026", "invalid"), ("hôm qua", "invalid"), ("", "absent")])
def test_date_refusals(raw, status):
    result = normalize_date(raw)
    assert result.status == status and result.value is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("14:30", "14:30"),
        ("9:05", "09:05"),
        ("14:30:05", "14:30:05"),
        ("14h30", "14:30"),
        ("14H30", "14:30"),
        ("14h", "14:00"),
        ("2:30 PM", "14:30"),
        ("02:30 CH", "14:30"),
        ("12:10 SA", "00:10"),
        ("12:10 PM", "12:10"),
        ("Giờ: 08:15", "08:15"),
    ],
)
def test_time_canonical(raw, expected):
    assert (normalize_time(raw).status, normalize_time(raw).value) == ("ok", expected)


@pytest.mark.parametrize(("raw", "status"), [("25:00", "invalid"), ("14:60", "invalid"), ("13:00 PM", "invalid"), ("chiều", "invalid"), (None, "absent")])
def test_time_refusals(raw, status):
    result = normalize_time(raw)
    assert result.status == status and result.value is None


def test_text_keeps_vietnamese_marks_and_uses_nfc():
    decomposed = "Cà phê"  # combining grave / circumflex
    result = normalize_text(f"  {decomposed}\n  sữa\t đá ")
    assert result.value == "Cà phê sữa đá"
    assert result.status == "ok"


@pytest.mark.parametrize("raw", [None, "", " \n\t "])
def test_text_absent(raw):
    assert normalize_text(raw).status == "absent"


def test_text_over_schema_limit_is_invalid():
    assert normalize_text("x" * 501).status == "invalid"


@pytest.mark.parametrize(
    ("raw", "status", "expected"),
    [
        ("45000", "ok", "45000"),
        ("45000.10", "ok", "45000.1"),
        ("4.5e4", "ok", "45000"),
        ("0.0", "ok", "0"),
        ("-5", "invalid", None),
        ("45.000,5", "invalid", None),
        ("", "absent", None),
    ],
)
def test_number_literal_is_exact_without_locale(raw, status, expected):
    result = normalize_number_literal(raw)
    assert (result.status, result.value) == (status, expected)


@pytest.mark.parametrize("precision", [6, 28, 50])
@pytest.mark.parametrize("normalizer", [normalize_money, normalize_quantity, normalize_number_literal])
def test_decimal_values_are_exact_independent_of_context(precision, normalizer):
    values = [
        "12345678901234567890123456789",  # previously silently rounded at precision 28
        "12345678901234567890123456789012",  # schema's 32-character boundary
        "12345678901234567890123456789.12",
    ]
    with localcontext() as context:
        context.prec = precision
        context.Emax, context.Emin = 9, -9
        context.traps[Inexact] = context.traps[Rounded] = True
        for raw in values:
            result = normalizer(raw)
            assert (result.status, result.value, result.raw) == ("ok", raw, raw)
            assert DECIMAL.fullmatch(result.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1e31", "1" + "0" * 31),
        ("1e32", None),
        ("1e-30", "0." + "0" * 29 + "1"),
        ("1e-31", None),
        ("1e1000000", None),
        ("1e-1000000", None),
        ("1e" + "9" * 5000, None),
        ("1e-" + "9" * 5000, None),
        ("0e1000000", "0"),
        ("0e-1000000", "0"),
        ("-0.0", "0"),
        ("123450000e-8", "1.2345"),
        ("1" + "0" * 5000 + "e-5000", "1"),
        ("0." + "0" * 5000 + "1e5001", "1"),
    ],
    ids=["integer-limit", "integer-overflow", "fraction-limit", "fraction-overflow",
         "large-positive-exponent", "large-negative-exponent", "unrepresentable-positive-exponent",
         "unrepresentable-negative-exponent", "positive-exponent-zero", "negative-exponent-zero",
         "signed-zero", "trailing-zeros", "coefficient-exponent-cancellation", "fraction-exponent-cancellation"],
)
@pytest.mark.parametrize("trap_invalid", [True, False])
def test_number_literal_bounds_before_expansion(raw, expected, trap_invalid):
    with localcontext() as context:
        context.traps[InvalidOperation] = trap_invalid
        result = normalize_number_literal(raw)
    assert result.raw == raw
    assert result.value == expected
    assert result.status == ("invalid" if expected is None else "ok")
    if expected is None:
        assert result.reason
    else:
        assert len(result.value) <= 32 and DECIMAL.fullmatch(result.value)


@pytest.mark.parametrize("normalizer", [normalize_money, normalize_quantity, normalize_number_literal])
def test_decimal_input_and_output_limits(normalizer):
    result = normalizer("9" * 33)
    assert result.status == "invalid" and result.value is None
    assert normalizer("0" * MAX_NUMBER_CHARS).value == "0"
    too_long = "0" * (MAX_NUMBER_CHARS + 1)
    result = normalizer(too_long)
    assert (result.status, result.value, result.raw) == ("invalid", None, too_long)
