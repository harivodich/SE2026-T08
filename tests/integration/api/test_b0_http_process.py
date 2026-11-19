"""Actual loopback HTTP; native OCR alone is replaced in a test-only process."""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image
import pytest

from vietdoc.contracts.compute import ComputeContracts


def fetch(url, body=None, token="test-only-token", capture=None):
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "multipart/form-data; boundary=VietDocFictionalBoundary"
    try:
        response = urlopen(Request(url, data=body, headers=headers), timeout=30)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read()
        if capture is not None:
            capture.write_bytes(raw)
        return response.code, json.loads(raw)


def multipart(meta, data):
    return (b'--VietDocFictionalBoundary\r\nContent-Disposition: form-data; name="request"\r\n\r\n'
            + json.dumps(meta).encode() + b'\r\n--VietDocFictionalBoundary\r\n'
            b'Content-Disposition: form-data; name="file"; filename="fictional-page"\r\n'
            b'Content-Type: application/octet-stream\r\n\r\n' + data + b'\r\n--VietDocFictionalBoundary--\r\n')


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("b0-http-process")
    release = root / "models/test-b0"
    release.mkdir(parents=True)
    (release / "rules.json").write_bytes(b"{}")
    (release / "manifest.json").write_text(json.dumps(dict(manifest_version=1, pipeline_manifest_id="test-b0",
        files=[dict(path="rules.json", size_bytes=2, sha256=hashlib.sha256(b"{}").hexdigest())])))
    log = (root / "process.log").open("wb")
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("fixture_process.py")), str(root)],
                               stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ))
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("Fixture HTTP process exited before readiness")
            try:
                port = json.loads((root / "port.json").read_text())
                base = f"http://127.0.0.1:{port}"
                if fetch(base + "/health/ready")[0] == 200:
                    break
            except (OSError, ValueError, URLError):
                pass
            time.sleep(.05)
        else:
            pytest.fail("Fixture HTTP process never became ready")
        yield base, root
    finally:
        try:
            process.stdin.write(b"stop\n")
            process.stdin.flush()
            process.communicate(timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.communicate(timeout=5)
        log.close()


def metadata(data, kind="receipt"):
    return dict(contract_version=1, job_id=str(uuid.uuid4()), run_id=str(uuid.uuid4()), attempt_id=str(uuid.uuid4()),
                document_type=kind, schema_version=f"{kind}.v1", language="vi", pipeline_manifest_id="test-b0",
                input_sha256=hashlib.sha256(data).hexdigest(), remaining_budget_ms=30000)


@pytest.mark.parametrize("kind", ["receipt", "invoice"])
@pytest.mark.parametrize("format", ["PNG", "JPEG", "PDF"])
def test_http_bytes_produce_actual_correlated_artifacts(server, kind, format):
    base, root = server
    with Image.new("RGB", (100,100), "white") as image, BytesIO() as stream:
        image.save(stream, format=format)
        data = stream.getvalue()
    meta = metadata(data, kind)
    code, response = fetch(base + "/internal/v1/compute", multipart(meta, data),
                           capture=root / f"{kind}-{format}-response.json")
    assert code == 200, response
    ComputeContracts().check_response(meta, response)
    assert response["result"]["payload"]["total_amount"] == "80000"
    for entry in response["artifacts"]:
        actual = (root / entry["asset_key"]).read_bytes()
        assert hashlib.sha256(actual).hexdigest() == entry["sha256"]
        assert len(actual) == entry["size_bytes"]
    # Keep sanitizeable bytes/manifest for Backend review in pytest's temp root.
    (root / f"{kind}-{format}-request.json").write_text(json.dumps(meta), encoding="utf-8")
    (root / f"{kind}-{format}-input.{format.lower()}").write_bytes(data)
    assert fetch(base + "/internal/v1/compute", multipart(meta, data))[0] == 503


@pytest.mark.parametrize("field", ["job_id", "run_id", "attempt_id"])
def test_http_rejects_noncanonical_uuid_without_creating_attempt(server, field):
    base, root = server
    with Image.new("RGB", (100, 100), "white") as image, BytesIO() as stream:
        image.save(stream, format="PNG")
        data = stream.getvalue()
    meta = metadata(data)
    meta[field] = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
    before = set((root / "attempts").iterdir())

    code, response = fetch(base + "/internal/v1/compute", multipart(meta, data))

    assert code == 422
    assert response["code"] == "INPUT_INVALID"
    assert response["attempt_id"] == (None if field == "attempt_id" else meta["attempt_id"])
    assert set((root / "attempts").iterdir()) == before


def test_http_failure_and_auth_do_not_poison_next_request(server):
    base, root = server
    bad = b"invalid image"
    code, response = fetch(base + "/internal/v1/compute", multipart(metadata(bad), bad),
                           capture=root / "invalid-input-error.json")
    assert code == 422 and response["code"] == "INPUT_INVALID"
    assert fetch(base + "/internal/v1/compute", multipart(metadata(bad), bad), token="wrong")[0] == 401
    assert fetch(base + "/health/ready")[0] == 200


def test_http_artifacts_remain_usable_by_existing_data_exporter(server):
    from vietdoc.pipeline.extraction.predictions import export_predictions
    base, root = server
    with Image.new("RGB", (100,100), "white") as image, BytesIO() as stream:
        image.save(stream, format="PNG")
        data = stream.getvalue()
    status, response = fetch(base + "/internal/v1/compute", multipart(metadata(data), data))
    assert status == 200
    entries = {e["kind"]: root / e["asset_key"] for e in response["artifacts"]}
    ocr = json.loads(entries["ocr"].read_bytes())
    prepared = json.loads(entries["transform"].read_bytes())
    (root / "dataset.json").write_text(json.dumps(dict(version="test-http.v1", samples=[dict(
        sample_id="fictional-receipt", document_type="receipt", schema_id="urn:vietdoc:business:v1")])))
    references = {kind: dict(path=entries[kind].relative_to(root).as_posix(),
                            sha256=hashlib.sha256(entries[kind].read_bytes()).hexdigest())
                  for kind in ("ocr", "transform")}
    (root / "ocr-inputs.json").write_text(json.dumps(dict(artifact_version="vietdoc.baseline-inputs.v1",
        ocr_version=ocr["ocr_version"], preprocess_version=prepared["preprocess_version"],
        samples=[dict(sample_id="fictional-receipt", ocr=references["ocr"], prepared=references["transform"])])))
    output = root / "data-export"
    artifact = export_predictions(root, Path("dataset.json"), output, ocr_inputs=Path("ocr-inputs.json"))
    assert artifact["artifact_version"] == "vietdoc.predictions.v1"
    assert artifact["predictions"][0]["payload"]["total_amount"] == "80000"
    diagnostic = json.loads((output / "ocr-diagnostics.json").read_bytes())
    assert diagnostic["predictions_sha256"] == hashlib.sha256((output / "predictions.json").read_bytes()).hexdigest()


def test_actual_cli_factory_reports_missing_native_release(tmp_path):
    import socket
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = dict(os.environ, VIETDOC_SERVICE_TOKEN="test-only-token", VIETDOC_HOST="127.0.0.1",
        VIETDOC_PORT=str(port), VIETDOC_MODELS_DIR=str(tmp_path / "models"),
        VIETDOC_ATTEMPTS_DIR=str(tmp_path / "attempts"), VIETDOC_PIPELINE_MANIFEST_ID="unprovisioned")
    with (tmp_path / "runtime.log").open("wb") as log:
        process = subprocess.Popen([sys.executable, "-m", "vietdoc.entrypoints.api"], env=environment,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert process.poll() is None, "CLI runtime exited before health check"
                try:
                    base = f"http://127.0.0.1:{port}"
                    if fetch(base + "/health/live") == (200, {"status": "UP"}):
                        break
                except (URLError, OSError):
                    pass
                time.sleep(.05)
            else:
                pytest.fail("CLI health deadline expired")
            code, ready = fetch(base + "/health/ready")
            assert code == 503 and ready["status"] == "NOT_READY"
            assert "MANIFEST_UNAVAILABLE" in ready["reasons"]
        finally:
            process.terminate()
            process.wait(timeout=10)
