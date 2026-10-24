"""Python side of the shared compute contract: same fictional fixtures Java will use."""

import copy
import json
from pathlib import Path

import pytest

from vietdoc.contracts.compute import (
    ERROR_SCHEMA,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    ComputeContracts,
    ContractError,
)

FIXTURES = Path(__file__).parent


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contracts() -> ComputeContracts:
    return ComputeContracts()


@pytest.mark.parametrize(
    ("schema_id", "fixture"),
    [
        (REQUEST_SCHEMA, "compute-request.json"),
        (RESPONSE_SCHEMA, "compute-response.json"),
        (ERROR_SCHEMA, "compute-error.json"),
    ],
)
def test_shared_fixtures_are_valid(contracts, schema_id, fixture):
    contracts.validate(schema_id, load(fixture))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("contract_version", 2),
        ("schema_version", "invoice.v1"),
        ("attempt_id", "not-a-uuid"),
        ("remaining_budget_ms", 0),
        ("input_sha256", "A" * 64),
        ("pipeline_manifest_id", "../escape"),
        ("language", "en"),
        ("unexpected", True),
    ],
)
def test_request_mutations_are_rejected(contracts, key, value):
    request = load("compute-request.json")
    request[key] = value
    with pytest.raises(ContractError):
        contracts.validate(REQUEST_SCHEMA, request)


def test_missing_required_request_key_is_rejected(contracts):
    request = load("compute-request.json")
    del request["input_sha256"]
    with pytest.raises(ContractError):
        contracts.validate(REQUEST_SCHEMA, request)


def test_money_as_number_is_rejected_inside_response(contracts):
    response = load("compute-response.json")
    response["result"]["payload"]["total_amount"] = 45000
    with pytest.raises(ContractError):
        contracts.validate(RESPONSE_SCHEMA, response)


def test_error_body_uses_schema_codes(contracts):
    assert "AI_NOT_READY" in contracts.error_codes
    with pytest.raises(ContractError):
        contracts.error_body("MADE_UP", "x", False)


def test_response_correlation_matches_request(contracts):
    contracts.check_response(load("compute-request.json"), load("compute-response.json"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["result"].__setitem__("run_id", "44444444-4444-4444-8444-444444444444"),
        lambda r: r.__setitem__("attempt_id", "44444444-4444-4444-8444-444444444444"),
        lambda r: r["result"]["provenance"].__setitem__("pipeline_manifest_id", "other.v1"),
        lambda r: r["artifacts"][1].__setitem__(
            "asset_key", "attempts/11111111-1111-4111-8111-111111111111/44444444-4444-4444-8444-444444444444/ocr.json"
        ),
        lambda r: r["artifacts"][1].__setitem__("asset_key", r["artifacts"][0]["asset_key"]),
        lambda r: r["canonical_page"].__setitem__("sha256", "1" * 64),
    ],
)
def test_response_correlation_mismatch_is_rejected(contracts, mutate):
    response = copy.deepcopy(load("compute-response.json"))
    mutate(response)
    with pytest.raises(ContractError):
        contracts.check_response(load("compute-request.json"), response)
