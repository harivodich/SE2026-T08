"""Private compute HTTP boundary: auth, limits, schema, hash, manifest, readiness, slot.

Pipelines used here are test doubles that return the shared fictional fixture; they
exercise wiring only and say nothing about OCR/model quality.
"""

import hashlib
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vietdoc.contracts.compute import ERROR_SCHEMA, ComputeContracts, default_contracts_dir
from vietdoc.entrypoints.api.app import NO_PIPELINE, create_app
from vietdoc.entrypoints.api.settings import Settings

TOKEN = "test-token-not-a-secret"
MANIFEST_ID = "fixture_pipeline.v1"
FIXTURES = Path(__file__).parents[2] / "contract"
DOCUMENT = b"\x89PNG fictional bytes"
CONTRACTS = ComputeContracts()


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def write_release(models: Path) -> None:
    root = models / MANIFEST_ID
    root.mkdir(parents=True)
    (root / "rules.json").write_bytes(b"{}")
    manifest = {
        "manifest_version": 1,
        "pipeline_manifest_id": MANIFEST_ID,
        "files": [{"path": "rules.json", "sha256": hashlib.sha256(b"{}").hexdigest(), "size_bytes": 2}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class StubPipeline:
    def __init__(self, response=None, error=None, gate=None):
        self.response = response if response is not None else fixture("compute-response.json")
        self.error = error
        self.gate = gate
        self.entered = threading.Event()

    def ready_reasons(self):
        return []

    def run(self, job):
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def make_client(tmp_path):
    clients = []

    def build(pipeline=None, token=TOKEN, release=True, max_input_bytes=1024):
        if release:
            write_release(tmp_path / "models")
        settings = Settings(
            service_token=token,
            models_dir=tmp_path / "models",
            attempts_dir=tmp_path / "attempts",
            contracts_dir=default_contracts_dir(),
            max_input_bytes=max_input_bytes,
        )
        client = TestClient(create_app(settings, pipeline))
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


def request_meta(document=DOCUMENT, **overrides):
    meta = fixture("compute-request.json")
    meta["input_sha256"] = hashlib.sha256(document).hexdigest()
    meta.update(overrides)
    return meta


def post(client, meta, document=DOCUMENT, token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = {"request": meta if isinstance(meta, str) else json.dumps(meta)}
    files = {"file": ("page.png", document, "image/png")} if document is not None else None
    return client.post("/internal/v1/compute", headers=headers, data=data, files=files)


def assert_error(response, status, code, retryable=None):
    assert response.status_code == status, response.text
    body = response.json()
    CONTRACTS.validate(ERROR_SCHEMA, body)
    assert body["code"] == code
    if retryable is not None:
        assert body["retryable"] is retryable
    return body


def test_live_is_up_and_ready_reports_missing_pipeline(make_client):
    client = make_client()
    assert client.get("/health/live").json() == {"status": "UP"}
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "NOT_READY"
    assert ready.json()["releases"] == [MANIFEST_ID]
    assert NO_PIPELINE in ready.json()["reasons"]
    assert ready.headers["X-Request-Id"]


def test_ready_lists_every_missing_dependency(make_client):
    client = make_client(token="", release=False)
    reasons = client.get("/health/ready").json()["reasons"]
    assert "service token is not configured" in reasons
    assert "no verified release under the models directory" in reasons


def test_ready_with_pipeline_release_and_token(make_client):
    assert make_client(pipeline=StubPipeline()).get("/health/ready").status_code == 200


def test_public_docs_are_disabled(make_client):
    client = make_client()
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_service_auth_is_required(make_client, token):
    body = assert_error(post(make_client(), request_meta(), token=token), 401, "SERVICE_AUTH_FAILED", False)
    assert body["attempt_id"] is None


def test_unconfigured_token_rejects_everything(make_client):
    assert_error(post(make_client(token=""), request_meta(), token="anything"), 401, "SERVICE_AUTH_FAILED")


def test_schema_invalid_metadata_echoes_parsed_attempt(make_client):
    body = assert_error(post(make_client(), request_meta(schema_version="invoice.v1")), 422, "INPUT_INVALID", False)
    assert body["attempt_id"] == fixture("compute-request.json")["attempt_id"]


@pytest.mark.parametrize("meta", ["not json", json.dumps([1, 2])])
def test_unparseable_metadata_is_input_invalid(make_client, meta):
    body = assert_error(post(make_client(), meta), 422, "INPUT_INVALID")
    assert body["attempt_id"] is None


def test_missing_file_part_is_input_invalid(make_client):
    assert_error(post(make_client(), request_meta(), document=None), 422, "INPUT_INVALID")


def test_hash_must_match_uploaded_bytes(make_client):
    assert_error(post(make_client(), request_meta(input_sha256="0" * 64)), 422, "INPUT_INVALID")


def test_document_over_limit_is_rejected(make_client):
    big = b"x" * 2000
    assert_error(post(make_client(), request_meta(big), document=big), 413, "INPUT_TOO_LARGE", False)


def test_body_far_over_limit_is_rejected_before_parsing(make_client):
    huge = b"x" * (200 * 1024)
    assert_error(post(make_client(), request_meta(huge), document=huge), 413, "INPUT_TOO_LARGE", False)


def test_unknown_manifest_is_unavailable(make_client):
    meta = request_meta(pipeline_manifest_id="not_installed.v1")
    assert_error(post(make_client(pipeline=StubPipeline()), meta), 422, "MANIFEST_UNAVAILABLE", False)


def test_valid_request_without_pipeline_is_not_ready(make_client):
    response = post(make_client(), request_meta())
    assert_error(response, 503, "AI_NOT_READY", True)
    assert response.headers["Retry-After"] == "5"


def test_pipeline_result_is_returned_after_contract_checks(make_client):
    response = post(make_client(pipeline=StubPipeline()), request_meta())
    assert response.status_code == 200, response.text
    assert response.json() == fixture("compute-response.json")


def test_mismatched_pipeline_output_is_output_invalid(make_client):
    output = fixture("compute-response.json")
    output["result"]["job_id"] = "44444444-4444-4444-8444-444444444444"
    assert_error(post(make_client(pipeline=StubPipeline(response=output)), request_meta()), 422, "OUTPUT_INVALID", False)


def test_pipeline_exception_is_internal_error(make_client):
    pipeline = StubPipeline(error=RuntimeError("boom"))
    assert_error(post(make_client(pipeline=pipeline), request_meta()), 500, "INTERNAL_ERROR", False)


def test_second_request_while_computing_is_busy(make_client):
    gate = threading.Event()
    pipeline = StubPipeline(gate=gate)
    client = make_client(pipeline=pipeline)
    first = {}
    worker = threading.Thread(target=lambda: first.setdefault("response", post(client, request_meta())))
    worker.start()
    assert pipeline.entered.wait(5)
    other = request_meta(attempt_id="55555555-5555-4555-8555-555555555555")
    response = post(client, other)
    gate.set()
    worker.join(5)
    assert_error(response, 503, "AI_BUSY", True)
    assert response.headers["Retry-After"] == "5"
    assert first["response"].status_code == 200


def test_reused_attempt_is_rejected(make_client):
    client = make_client(pipeline=StubPipeline())
    assert post(client, request_meta()).status_code == 200
    assert_error(post(client, request_meta()), 503, "AI_BUSY", False)
