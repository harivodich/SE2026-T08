"""Serving consumer acceptance with real FastAPI/decode/B0/artifacts; OCR is a fixture.

No native recognition/model quality claim. Requires local hard-link publication.
"""
import hashlib
import json
import threading
import uuid
from contextlib import contextmanager
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from vietdoc.contracts.compute import ComputeContracts, default_contracts_dir
from vietdoc.contracts.ocr import OcrBlock, OcrPage, UnreadableRegion
from vietdoc.entrypoints.api.app import create_app
from vietdoc.entrypoints.api.settings import Settings
from vietdoc.ml.release_manifest import load_release
from vietdoc.pipeline import composition
from vietdoc.pipeline.service import ComputeFailure

QUAD = ((.1, .4), (.8, .4), (.8, .5), (.1, .5))
TOKEN = "fixture-consumer-token"


def release_at(root, profile, extra=None):
    root.mkdir(parents=True)
    files = {"pipeline.json": json.dumps(profile).encode(), **(extra or {})}
    entries = []
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entries.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)})
    (root / "manifest.json").write_text(json.dumps({"manifest_version": 1,
        "pipeline_manifest_id": root.name, "files": entries}), encoding="utf-8")
    return load_release(root.parent, root.name)


class Engine:
    ready = False
    mode = "partial"
    failure = None
    entered = None
    gate = None
    def load(self): self.ready = True
    def close(self): self.ready = False
    def recognize(self, loaded, *, remaining_budget_ms):
        self.loaded = loaded
        if self.entered is not None:
            self.entered.set()
            assert self.gate.wait(5)
        if self.failure:
            raise self.failure
        blocks = (OcrBlock("total", "Tổng tiền: 80.000", QUAD, .9, None),)
        unreadable = (UnreadableRegion("u1", QUAD, 0, None),)
        if self.mode in ("unreadable", "empty"):
            blocks = ()
        if self.mode in ("complete", "empty"):
            unreadable = ()
        width = loaded.metadata.canonical.width + (1 if self.mode == "dimensions" else 0)
        page = OcrPage(0, width, loaded.metadata.canonical.height, "fixture.ocr.v2",
                       blocks, artifact_version=2, unreadable_regions=unreadable)
        if self.mode == "unknown":
            object.__setattr__(page, "artifact_version", 99)
        return page


def document():
    with BytesIO() as stream:
        with Image.new("RGB", (100, 100), "white") as image:
            image.save(stream, "PNG")
        return stream.getvalue()


def meta(data, **changes):
    value = {"contract_version": 1, "job_id": str(uuid.uuid4()), "run_id": str(uuid.uuid4()),
                 "attempt_id": str(uuid.uuid4()), "document_type": "receipt", "schema_version": "receipt.v1",
                 "language": "vi", "input_sha256": hashlib.sha256(data).hexdigest(),
                 "pipeline_manifest_id": "consumer", "remaining_budget_ms": 30000}
    value.update(changes)
    return value


def post(client, metadata, data):
    return client.post("/internal/v1/compute", headers={"Authorization": f"Bearer {TOKEN}"},
        data={"request": json.dumps(metadata)}, files={"file": ("page.png", data, "image/png")})


@contextmanager
def client_at(tmp_path, monkeypatch, engine, *, profile=None, extractor=None):
    profile = profile or dict(composition.PROFILE, profile_version=2, ocr_artifact_version=2)
    release = release_at(tmp_path / "models/consumer", profile)
    monkeypatch.setattr(composition, "build_engine", lambda release: engine)
    pipeline = composition.ManagedPipeline("consumer", ocr_artifact_version=2,
        extractor_factory=(lambda release: extractor) if extractor else None,
        extractor_version=extractor.version if extractor else composition.BASELINE_VERSION,
        normalizer_version=getattr(extractor, "normalizer_version", composition.POLICY_VERSION))
    settings = Settings(TOKEN, release.root.parent, tmp_path / "attempts", default_contracts_dir())
    with TestClient(create_app(settings, pipeline)) as client:
        yield client, release, pipeline
    assert not engine.ready


@pytest.mark.parametrize("mode", ["complete", "partial", "unreadable", "empty"])
@pytest.mark.parametrize("kind", ["receipt", "invoice"])
def test_serving_partial_consumer(tmp_path, monkeypatch, mode, kind):
    engine = Engine()
    engine.mode = mode
    with client_at(tmp_path, monkeypatch, engine) as (client, _release, _pipeline):
        assert client.get("/health/ready").status_code == 200
        data = document()
        request = meta(data, document_type=kind, schema_version=f"{kind}.v1")
        response = post(client, request, data)
        assert response.status_code == 200, response.text
        body = response.json()
        ComputeContracts().check_response(request, body)
        assert body["result"]["payload"]["total_amount"] == (None if mode in ("empty", "unreadable") else "80000")
        issues = body["result"]["issues"]
        assert any(i["code"] == "FIELD_NOT_LOCATED" for i in issues)
        assert any(i["code"] == "OCR_UNREADABLE_REGIONS" for i in issues) == (mode in ("partial", "unreadable"))
        for field in body["result"]["field_metadata"]:
            assert field["confidence"] is None and field["confidence_method"] is None
            if mode in ("partial", "unreadable"):
                assert "SOURCE_OCR_INCOMPLETE" in field["review_flags"]
        directory = tmp_path / "attempts" / request["job_id"] / request["attempt_id"]
        for artifact in body["artifacts"]:
            raw = (directory / artifact["asset_key"].rsplit("/", 1)[-1]).read_bytes()
            assert artifact["sha256"] == hashlib.sha256(raw).hexdigest()
            assert artifact["size_bytes"] == len(raw)
        stored = OcrPage.from_dict(json.loads((directory / "ocr.json").read_bytes()))
        assert (stored.width, stored.height) == (body["canonical_page"]["width"], body["canonical_page"]["height"])
        assert stored.recognition_status == {"complete":"complete", "partial":"partial", "unreadable":"unreadable", "empty":"complete"}[mode]
        if mode in ("unreadable", "empty"):
            assert all(f["source_regions"] == [] for f in body["result"]["field_metadata"])
    with pytest.raises(ValueError):
        engine.loaded.canonical.getpixel((0, 0))


@pytest.mark.parametrize("mode", ["unknown", "dimensions"])
def test_bad_ocr_cannot_publish(tmp_path, monkeypatch, mode):
    engine = Engine()
    engine.mode = mode
    with client_at(tmp_path, monkeypatch, engine) as (client, _, __):
        data = document()
        response = post(client, meta(data), data)
        assert response.status_code == 422
        assert response.json()["code"] == "OUTPUT_INVALID"
        assert not list((tmp_path / "attempts").rglob("canonical.png"))


def test_unsupported_profile_not_ready_and_no_model_load(tmp_path, monkeypatch):
    engine = Engine()
    profile = dict(composition.PROFILE, profile_version=99)
    with client_at(tmp_path, monkeypatch, engine, profile=profile) as (client, _, __):
        assert client.get("/health/ready").status_code == 503
        data = document()
        response = post(client, meta(data), data)
        assert response.status_code == 503 and response.json()["code"] == "AI_NOT_READY"
        assert not engine.ready


@pytest.mark.parametrize("failure, status, code", [
    (ComputeFailure("COMPUTE_TIMEOUT"), 504, "COMPUTE_TIMEOUT"),
    (MemoryError(), 500, "MODEL_OOM"),
])
def test_stage_failure_releases_slot_and_images(tmp_path, monkeypatch, failure, status, code):
    engine = Engine()
    engine.failure = failure
    with client_at(tmp_path, monkeypatch, engine) as (client, _, __):
        data = document()
        for _ in range(2):
            response = post(client, meta(data), data)
            assert response.status_code == status and response.json()["code"] == code
            with pytest.raises(ValueError):
                engine.loaded.canonical.getpixel((0, 0))


def test_hash_and_manifest_rejected_before_engine(tmp_path, monkeypatch):
    engine = Engine()
    with client_at(tmp_path, monkeypatch, engine) as (client, _, __):
        data = document()
        for changes, code in [({"input_sha256":"0"*64}, "INPUT_INVALID"),
                              ({"pipeline_manifest_id":"missing"}, "MANIFEST_UNAVAILABLE")]:
            response = post(client, meta(data, **changes), data)
            assert response.status_code == 422 and response.json()["code"] == code
        assert not hasattr(engine, "loaded")


@pytest.mark.parametrize("valid", [False, True])
def test_strict_raw_model_over_http_preserves_canonical_decimals(tmp_path, monkeypatch, valid):
    from types import SimpleNamespace

    from vietdoc.ml.compute_extractor import (
        NORMALIZER_VERSION,
        VERSION,
        QwenComputeExtractor,
    )
    from vietdoc.ml.model_loading import Generation
    schema = default_contracts_dir() / "business.schema.json"
    scalars, _ = ComputeContracts().business_fields("receipt")
    original = dict({key: None for key in scalars}, total_amount="1.234", items=[{
        "description": "Decimal quantity", "quantity": "2.000", "unit": None,
        "unit_price": "0.617", "line_total": "1.234"}])
    raw = json.dumps(original) if valid else '{"total_amount":80000,"items":[]}'
    extractor = QwenComputeExtractor(None, config=None, snapshot=None, config_sha256="a"*64,
                                     snapshot_manifest_sha256="b"*64)
    calls = []
    def generate(*args, **kwargs):
        calls.append(True)
        # Same failure category as M1: syntactically valid JSON, wrong raw schema.
        return Generation(raw, "stop", 5, 5, .01, {})
    loader = SimpleNamespace(ready=True,
        config=SimpleNamespace(schema_path=schema, schema_sha256=hashlib.sha256(schema.read_bytes()).hexdigest()),
        generate=generate, close=lambda: calls.append("close"))
    monkeypatch.setattr(extractor, "load", lambda: setattr(extractor, "loader", loader))
    engine = Engine()
    profile = dict(composition.PROFILE, profile_version=2, ocr_artifact_version=2,
                   extractor_version=VERSION, normalizer_version=NORMALIZER_VERSION)
    with client_at(tmp_path, monkeypatch, engine, profile=profile, extractor=extractor) as (client, _, __):
        data = document()
        for _ in range(2):
            response = post(client, meta(data), data)
            if valid:
                assert response.status_code == 200
                result = response.json()["result"]
                assert result["payload"] == original
                assert result["provenance"]["normalizer_version"] == NORMALIZER_VERSION
            else:
                assert response.status_code == 422 and response.json()["code"] == "OUTPUT_INVALID"
        if not valid:
            assert not list((tmp_path / "attempts").rglob("canonical.png"))
    assert calls == [True, True, "close"]


def test_busy_keeps_single_running_consumer(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    engine = Engine()
    engine.failure = ComputeFailure("COMPUTE_TIMEOUT")
    engine.entered, engine.gate = threading.Event(), threading.Event()
    with client_at(tmp_path, monkeypatch, engine) as (client, _, __):
        data = document()
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(post, client, meta(data), data)
            try:
                assert engine.entered.wait(5)
                rejected = post(client, meta(data), data)
                assert rejected.status_code == 503 and rejected.json()["code"] == "AI_BUSY"
            finally:
                engine.gate.set()
            assert running.result(timeout=5).status_code == 504
        assert post(client, meta(data), data).status_code == 504
