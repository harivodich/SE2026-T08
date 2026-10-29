"""Private compute HTTP boundary: auth, limits, schema, hash, manifest, readiness, slot.

Pipelines used here are test doubles that return the shared fictional fixture; they
exercise wiring only and say nothing about OCR/model quality.
"""

import hashlib
import errno
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request

from vietdoc.contracts.compute import ERROR_SCHEMA, ComputeContracts, default_contracts_dir
from vietdoc.entrypoints.api.app import NO_PIPELINE, create_app
from vietdoc.entrypoints.api.settings import Settings
import vietdoc.entrypoints.api.app as app_module

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


def test_missing_ocr_artifact_returns_output_invalid(make_client):
    output = fixture("compute-response.json")
    output["artifacts"][1]["kind"] = "raw_prediction"
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


@pytest.mark.parametrize("error", [OSError(errno.ENOSPC, "private disk path"), PermissionError(errno.EACCES, "private path")])
def test_storage_parse_failure_is_service_error(make_client, monkeypatch, error):
    pipeline = StubPipeline()
    client = make_client(pipeline=pipeline)
    async def fail_form(*args, **kwargs):
        raise error
    with monkeypatch.context() as patch:
        patch.setattr(Request, "form", fail_form)
        response = post(client, request_meta())
    assert_error(response, 503, "AI_NOT_READY", True)
    assert "private" not in response.text and not pipeline.entered.is_set()
    assert post(client, request_meta()).status_code == 200


@pytest.mark.parametrize("stage", ["write", "read", "close"])
def test_storage_upload_failure_closes_file_and_preserves_capacity(make_client, monkeypatch, stage):
    pipeline = StubPipeline()
    client = make_client(pipeline=pipeline)
    files = []
    async def fail_io(upload, *args, **kwargs):
        files.append(upload.file)
        raise OSError(errno.ENOSPC, "private upload path")
    with monkeypatch.context() as patch:
        patch.setattr(UploadFile, stage, fail_io)
        response = post(client, request_meta())
    assert_error(response, 503, "AI_NOT_READY", True)
    assert files and all(file.closed for file in files)
    assert not pipeline.entered.is_set() and "private" not in response.text
    assert post(client, request_meta()).status_code == 200


def test_storage_cleanup_failure_keeps_primary_input_error(make_client, monkeypatch):
    client = make_client(pipeline=StubPipeline())
    files = []
    async def fail_close(upload):
        files.append(upload.file)
        raise OSError(errno.EACCES, "private cleanup path")
    with monkeypatch.context() as patch:
        patch.setattr(UploadFile, "close", fail_close)
        response = post(client, "not json")
    assert_error(response, 422, "INPUT_INVALID", False)
    assert files and all(file.closed for file in files)
    assert post(client, request_meta()).status_code == 200


@pytest.mark.parametrize(("error", "status", "code"), [
    (HTTPException(400, "malformed"), 422, "INPUT_INVALID"),
    (RuntimeError("private programming failure"), 500, "INTERNAL_ERROR"),
])
def test_storage_parser_does_not_misclassify_unexpected_error(make_client, monkeypatch, error, status, code):
    client = make_client()
    async def fail_form(*args, **kwargs):
        raise error
    monkeypatch.setattr(Request, "form", fail_form)
    response = post(client, request_meta())
    assert_error(response, status, code, False)
    assert "private" not in response.text


@pytest.mark.parametrize("kind", ["deep", "duplicate"])
def test_metadata_decoder_limits_return_typed_error_and_recover(make_client, kind):
    pipeline = StubPipeline()
    client = make_client(pipeline=pipeline)
    if kind == "deep":
        raw = '{"x":' + '[' * 5000 + '0' + ']' * 5000 + '}'
    else:
        raw = json.dumps(request_meta())
        raw = raw.replace('"contract_version": 1', '"contract_version": 1, "contract_version": 1')
    assert len(raw.encode()) < 16 * 1024
    assert_error(post(client, raw), 422, "INPUT_INVALID", False)
    assert not pipeline.entered.is_set()
    assert post(client, request_meta()).status_code == 200


@pytest.mark.parametrize("depth", [7, 8, 9])
def test_metadata_depth_boundary(depth):
    from vietdoc.entrypoints.api.metadata import decode_metadata
    raw = '[' * depth + '0' + ']' * depth
    if depth > 8:
        with pytest.raises(ValueError):
            decode_metadata(raw)
    else:
        assert decode_metadata(raw) == json.loads(raw)


def test_metadata_scanner_ignores_strings_and_escape_sequences():
    from vietdoc.entrypoints.api.metadata import decode_metadata
    value = {'text': '[{' * 30 + ' "quoted" \\ ending'}
    assert decode_metadata(json.dumps(value)) == value
    with pytest.raises(ValueError):
        decode_metadata('{"x": [1}')


class BudgetClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self):
        self.now += 0.2


@pytest.mark.parametrize("stage", ["ingress", "queue", "pipeline", "validation", "serialization"])
def test_deadline_covers_entire_request_and_recovers(make_client, monkeypatch, stage):
    clock = BudgetClock()
    monkeypatch.setattr(app_module, "time", SimpleNamespace(monotonic=clock))
    trigger = [True]
    class TimedPipeline(StubPipeline):
        def run(self, job):
            result = super().run(job)
            if stage == "pipeline" and trigger[0]:
                clock.advance()
            return result
    pipeline = TimedPipeline()
    client = make_client(pipeline=pipeline)
    events = []
    original_form = Request.form
    original_thread = app_module.run_in_threadpool
    original_validate = ComputeContracts.check_response
    original_render = app_module.JSONResponse.render
    async def delayed_form(*args, **kwargs):
        result = await original_form(*args, **kwargs)
        clock.advance()
        return result
    async def delayed_worker(func, *args, **kwargs):
        if func.__name__ == "run":
            clock.advance()
        return await original_thread(func, *args, **kwargs)
    def delayed_validate(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        clock.advance()
        return result
    def delayed_render(response, body):
        result = original_render(response, body)
        if isinstance(body, dict) and "result" in body:
            clock.advance()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(app_module.log, "info", lambda event, **kwargs: events.append(event))
        if stage == "ingress":
            patch.setattr(Request, "form", delayed_form)
        elif stage == "queue":
            patch.setattr(app_module, "run_in_threadpool", delayed_worker)
        elif stage == "validation":
            patch.setattr(ComputeContracts, "check_response", delayed_validate)
        elif stage == "serialization":
            patch.setattr(app_module.JSONResponse, "render", delayed_render)
        response = post(client, request_meta(remaining_budget_ms=100))
    assert_error(response, 504, "COMPUTE_TIMEOUT", False)
    assert "compute_succeeded" not in events
    assert pipeline.entered.is_set() == (stage not in ("ingress", "queue"))
    trigger[0] = False
    other = "55555555-5555-4555-8555-555555555555"
    old = pipeline.response["attempt_id"]
    pipeline.response["attempt_id"] = other
    pipeline.response["canonical_page"]["asset_key"] = pipeline.response["canonical_page"]["asset_key"].replace(old, other)
    for artifact in pipeline.response["artifacts"]:
        artifact["asset_key"] = artifact["asset_key"].replace(old, other)
    assert post(client, request_meta(attempt_id=other, remaining_budget_ms=100)).status_code == 200


def test_deadline_passes_original_budget_to_worker(make_client, monkeypatch):
    clock = BudgetClock()
    monkeypatch.setattr(app_module, "time", SimpleNamespace(monotonic=clock))
    deadlines = []
    class RecordingPipeline(StubPipeline):
        def run(self, job):
            deadlines.append(job.deadline)
            return super().run(job)
    client = make_client(pipeline=RecordingPipeline())
    assert post(client, request_meta(remaining_budget_ms=100)).status_code == 200
    assert deadlines == [pytest.approx(1000.1)]


def test_streamed_oversize_keeps_input_classification(make_client):
    pipeline = StubPipeline()
    client = make_client(pipeline=pipeline)
    chunks = iter([
        b'--bounded\r\nContent-Disposition: form-data; name="file"; filename="page.png"\r\n\r\n',
        b'x' * (200 * 1024),
        b'\r\n--bounded--\r\n',
    ])
    response = client.post('/internal/v1/compute', content=chunks, headers={
        'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'multipart/form-data; boundary=bounded',
    })
    assert_error(response, 413, "INPUT_TOO_LARGE", False)
    assert not pipeline.entered.is_set()


def test_malformed_multipart_keeps_input_classification(make_client):
    response = make_client().post('/internal/v1/compute', content=b'not multipart', headers={
        'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'multipart/form-data',
    })
    assert_error(response, 422, "INPUT_INVALID", False)
