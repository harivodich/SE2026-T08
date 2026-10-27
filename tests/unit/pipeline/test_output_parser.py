"""Model raw output → business payload: strict shape, no repair, normalized values."""

import json

import pytest

from vietdoc.contracts.compute import BUSINESS_SCHEMA, ComputeContracts
from vietdoc.pipeline.extraction.output_parser import MAX_RAW_CHARS, parse_model_output
from vietdoc.pipeline.normalization import POLICY_VERSION

CONTRACTS = ComputeContracts()


def receipt(**overrides):
    payload = {
        "merchant_name": "CỬA HÀNG MẪU",
        "merchant_address": None,
        "transaction_date": "06/10/2026",
        "transaction_time": None,
        "total_amount": "45.000",
        "items": [
            {"description": "Cà phê", "quantity": "3", "unit": "ly", "unit_price": "15.000", "line_total": "45.000"}
        ],
    }
    payload.update(overrides)
    return payload


def invoice():
    return {
        "invoice_number": "HD-0001",
        "issue_date": "Ngày 06 tháng 10 năm 2026",
        "seller_name": "CÔNG TY MẪU",
        "buyer_name": None,
        "subtotal": "100.000",
        "tax_amount": "8.000",
        "discount_amount": None,
        "total_amount": "108.000",
        "items": [],
    }


def parse(raw, document_type="receipt", finish_reason=None):
    return parse_model_output(raw, document_type, CONTRACTS, finish_reason=finish_reason)


def test_plain_json_is_normalized_and_raw_values_kept():
    result = parse(json.dumps(receipt(), ensure_ascii=False))
    assert result.status == "ok" and result.raw_json_valid and not result.fenced
    assert result.payload == {
        "merchant_name": "CỬA HÀNG MẪU",
        "merchant_address": None,
        "transaction_date": "2026-10-06",
        "transaction_time": None,
        "total_amount": "45000",
        "items": [{"description": "Cà phê", "quantity": "3", "unit": "ly", "unit_price": "15000", "line_total": "45000"}],
    }
    assert result.raw_values["/total_amount"] == "45.000"
    assert result.raw_values["/items/0/unit_price"] == "15.000"
    assert result.raw_values["/merchant_address"] is None
    assert result.issues == ()
    assert result.normalizer_version == POLICY_VERSION
    CONTRACTS.validate(BUSINESS_SCHEMA, result.payload)


def test_invoice_is_supported():
    result = parse(json.dumps(invoice(), ensure_ascii=False), "invoice")
    assert result.status == "ok"
    assert result.payload["issue_date"] == "2026-10-06"
    assert result.payload["total_amount"] == "108000"


def test_single_fenced_block_is_accepted_and_flagged():
    raw = "```json\n" + json.dumps(receipt(), ensure_ascii=False) + "\n```"
    result = parse(raw)
    assert result.status == "ok" and result.fenced and result.raw_json_valid


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "Here is the JSON: {}", "I cannot read this receipt."],
)
def test_text_without_standalone_json_is_no_json(raw):
    result = parse(raw)
    assert result.status == "no_json" and result.payload is None and not result.raw_json_valid


@pytest.mark.parametrize(
    "raw",
    [
        '{"merchant_name": "A",}',
        '{"merchant_name": "A", "merchant_name": "B"}',
        '{"total_amount": NaN}',
        "[" * 5000 + "]" * 5000,
    ],
    ids=["trailing-comma", "duplicate-key", "nan", "deep-nesting"],
)
def test_malformed_json_is_not_repaired(raw):
    result = parse(raw)
    assert result.status == "malformed_json" and result.payload is None and not result.raw_json_valid


def test_length_truncation_is_reported_even_if_text_parses():
    result = parse(json.dumps(receipt()), finish_reason="length")
    assert result.status == "truncated" and result.payload is None


def test_oversized_output_is_rejected_before_parsing():
    result = parse("{" + " " * MAX_RAW_CHARS + "}")
    assert result.status == "too_large" and result.payload is None


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2],
        {k: v for k, v in receipt().items() if k != "transaction_time"},
        receipt(tax_code="0101234567"),
        receipt(merchant_name=True),
        receipt(merchant_name=123),
        receipt(items={"description": "x"}),
        receipt(items=[{"description": "x"}]),
        receipt(items=[receipt()["items"][0] | {"vat": "8"}]),
        receipt(items=[receipt()["items"][0]] * 31),
    ],
)
def test_invalid_shape_is_schema_invalid(payload):
    result = parse(json.dumps(payload, ensure_ascii=False))
    assert result.status == "schema_invalid" and result.payload is None and result.reason
    assert result.raw_json_valid


def test_unknown_document_type_is_rejected():
    with pytest.raises(ValueError):
        parse(json.dumps(receipt()), "bank_statement")


def test_json_numbers_in_decimal_fields_are_read_exactly():
    raw = json.dumps(receipt(total_amount=45000)).replace("45000", "45000.10")
    result = parse(raw)
    assert result.status == "ok"
    assert result.payload["total_amount"] == "45000.1"
    assert result.raw_values["/total_amount"] == "45000.10"


def test_negative_json_number_becomes_null_with_issue():
    result = parse(json.dumps(receipt(total_amount=-5)))
    assert result.status == "ok" and result.payload["total_amount"] is None
    assert [issue["code"] for issue in result.issues] == ["VALUE_INVALID"]


@pytest.mark.parametrize("literal", ["12345678901234567890123456789", "12345678901234567890123456789012"])
@pytest.mark.parametrize("quoted", [False, True])
def test_large_decimal_values_keep_all_digits(literal, quoted):
    raw = json.dumps(receipt(total_amount="NUMBER_LITERAL"))
    raw = raw.replace('"NUMBER_LITERAL"', json.dumps(literal) if quoted else literal)
    result = parse(raw)
    assert result.status == "ok" and result.raw_json_valid
    assert result.payload["total_amount"] == literal
    assert result.raw_values["/total_amount"] == literal
    assert result.normalizer_version == "vi-VND.v2"
    assert result.issues == ()
    CONTRACTS.validate(BUSINESS_SCHEMA, result.payload)


@pytest.mark.parametrize("literal", ["1e1000000", "1e-1000000", "1e" + "9" * 5000, "9" * 33])
def test_unbounded_json_number_becomes_null_with_issue(literal):
    raw = json.dumps(receipt(total_amount="NUMBER_LITERAL")).replace('"NUMBER_LITERAL"', literal)
    result = parse(raw)
    assert result.status == "ok" and result.raw_json_valid
    assert result.payload["total_amount"] is None
    assert result.raw_values["/total_amount"] == literal
    assert [(issue["code"], issue["paths"]) for issue in result.issues] == [
        ("VALUE_INVALID", ["/total_amount"])
    ]
    CONTRACTS.validate(BUSINESS_SCHEMA, result.payload)


def test_refused_values_become_null_with_issues_and_keep_raw():
    item = receipt()["items"][0] | {"quantity": "2.000"}
    result = parse(json.dumps(receipt(transaction_date="31/02/2026", total_amount="abc", items=[item]), ensure_ascii=False))
    assert result.status == "ok"
    assert result.payload["transaction_date"] is None
    assert result.payload["items"][0]["quantity"] is None
    assert result.raw_values["/items/0/quantity"] == "2.000"
    codes = {issue["paths"][0]: issue["code"] for issue in result.issues}
    assert codes == {
        "/transaction_date": "VALUE_INVALID",
        "/total_amount": "VALUE_INVALID",
        "/items/0/quantity": "VALUE_AMBIGUOUS",
    }
    for issue in result.issues:
        assert set(issue) == {"id", "code", "severity", "paths", "message"}
        assert issue["id"] == f"{issue['code']}:{issue['paths'][0]}"
        assert issue["severity"] == "warning"
    CONTRACTS.validate(BUSINESS_SCHEMA, result.payload)


def test_absent_values_are_null_without_issue():
    result = parse(json.dumps(receipt(merchant_name="", transaction_time="  "), ensure_ascii=False))
    assert result.payload["merchant_name"] is None and result.payload["transaction_time"] is None
    assert result.issues == ()


def test_brackets_inside_strings_do_not_count_as_nesting():
    deep_text = "[" * 50 + '\\"{' * 20
    result = parse(json.dumps(receipt(merchant_name=deep_text)))
    assert result.status == "ok"
    assert result.payload["merchant_name"] == deep_text


def test_valid_json_over_depth_limit_is_rejected_on_every_platform():
    result = parse('{"a": ' * 9 + "1" + "}" * 9)
    assert result.status == "malformed_json" and result.reason == "nesting too deep"
