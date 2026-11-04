"""Python adapter for the private compute contract (specs/contracts, Draft 2020-12).

The neutral JSON Schemas are authoritative; this module only loads and validates
them with a real Draft 2020-12 validator and a local URN registry (no network refs).
Semantic checks (hash, manifest, correlation, asset containment) belong to callers.
No web, ORM or model framework imports here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import best_match
from referencing import Registry, Resource

CONTRACT_VERSION = 1
BUSINESS_SCHEMA = "urn:vietdoc:business:v1"
REQUEST_SCHEMA = "urn:vietdoc:compute-request:v1"
RESPONSE_SCHEMA = "urn:vietdoc:compute-response:v1"
ERROR_SCHEMA = "urn:vietdoc:compute-error:v1"
_SCHEMA_FILES = (
    "business",
    "extraction-result",
    "compute-request",
    "compute-response",
    "compute-error",
)


class ContractError(ValueError):
    """Instance does not match a contract schema; `path` is a JSON Pointer."""

    def __init__(self, schema_id: str, path: str, message: str) -> None:
        super().__init__(f"{schema_id} {path}: {message}")
        self.schema_id = schema_id
        self.path = path


def default_contracts_dir() -> Path:
    configured = os.environ.get("VIETDOC_CONTRACTS_DIR")
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "specs" / "contracts"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("specs/contracts not found; set VIETDOC_CONTRACTS_DIR")


class ComputeContracts:
    def __init__(self, directory: Path | None = None) -> None:
        directory = directory or default_contracts_dir()
        schemas: dict[str, dict[str, Any]] = {}
        for name in _SCHEMA_FILES:
            schema = json.loads((directory / f"{name}.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            schemas[schema["$id"]] = schema
        registry = Registry().with_resources(
            (schema_id, Resource.from_contents(schema)) for schema_id, schema in schemas.items()
        )
        self._validators = {
            schema_id: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
            for schema_id, schema in schemas.items()
        }
        self.error_codes = frozenset(
            schemas[ERROR_SCHEMA]["properties"]["code"]["enum"]
        )
        self._business = schemas[BUSINESS_SCHEMA]["$defs"]

    def business_fields(self, document_type: str) -> tuple[dict[str, str], dict[str, str]]:
        """(scalar field → $defs kind, item field → $defs kind) for receipt/invoice."""
        definition = {"receipt": "Receipt", "invoice": "Invoice"}.get(document_type)
        if definition is None:
            raise ValueError(f"unsupported document_type: {document_type!r}")

        def kinds(properties: Mapping[str, Any]) -> dict[str, str]:
            return {key: spec["$ref"].rsplit("/", 1)[-1] for key, spec in properties.items()}

        scalars = kinds(self._business[definition]["properties"])
        scalars.pop("items")
        return scalars, kinds(self._business["LineItem"]["properties"])

    def validate(self, schema_id: str, instance: Any) -> None:
        error = best_match(self._validators[schema_id].iter_errors(instance))
        if error is not None:
            path = "".join(f"/{part}" for part in error.absolute_path) or "/"
            raise ContractError(schema_id, path, error.message)

    def error_body(
        self, code: str, message: str, retryable: bool, attempt_id: str | None = None
    ) -> dict[str, Any]:
        body = {
            "contract_version": CONTRACT_VERSION,
            "attempt_id": attempt_id,
            "code": code,
            "message": message,
            "retryable": retryable,
        }
        self.validate(ERROR_SCHEMA, body)
        return body

    def check_response(self, request: Mapping[str, Any], response: Any) -> None:
        """Schema plus the correlation rules the schema cannot express."""
        self.validate(RESPONSE_SCHEMA, response)
        result = response["result"]
        expected = {
            "/attempt_id": (response["attempt_id"], request["attempt_id"]),
            "/result/run_id": (result["run_id"], request["run_id"]),
            "/result/job_id": (result["job_id"], request["job_id"]),
            "/result/document_type": (result["document_type"], request["document_type"]),
            "/result/schema_version": (result["schema_version"], request["schema_version"]),
            "/result/provenance/pipeline_manifest_id": (
                result["provenance"]["pipeline_manifest_id"],
                request["pipeline_manifest_id"],
            ),
        }
        for path, (actual, wanted) in expected.items():
            if actual != wanted:
                raise ContractError(RESPONSE_SCHEMA, path, "does not echo the request")
        prefix = f"attempts/{request['job_id']}/{request['attempt_id']}/"
        artifacts = response["artifacts"]
        if not any(artifact["kind"] == "ocr" for artifact in artifacts):
            raise ContractError(RESPONSE_SCHEMA, "/artifacts", "must include an OCR artifact")
        keys = [artifact["asset_key"] for artifact in artifacts]
        if len(set(keys)) != len(keys):
            raise ContractError(RESPONSE_SCHEMA, "/artifacts", "duplicate artifact keys")
        for index, key in enumerate(keys):
            if not key.startswith(prefix) or ".." in key.split("/"):
                raise ContractError(RESPONSE_SCHEMA, f"/artifacts/{index}/asset_key", "outside attempt prefix")
        page = response["canonical_page"]
        matches = [
            artifact
            for artifact in artifacts
            if artifact["kind"] == "canonical_page"
            and artifact["asset_key"] == page["asset_key"]
            and artifact["sha256"] == page["sha256"]
        ]
        if len(matches) != 1 or sum(a["kind"] == "canonical_page" for a in artifacts) != 1:
            raise ContractError(RESPONSE_SCHEMA, "/canonical_page", "must match exactly one artifact")
