"""Strict model seam tests use recorded raw strings, never weights/quality claims."""
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from vietdoc.contracts.compute import default_contracts_dir
from vietdoc.contracts.ocr import OcrPage
from vietdoc.ml.compute_extractor import VERSION, QwenComputeExtractor
from vietdoc.ml.model_loading import Generation
from vietdoc.pipeline.composition import PROFILE, ManagedPipeline
from vietdoc.pipeline.service import ComputeFailure


def extractor_with_raw(raw):
    extractor = QwenComputeExtractor(None, config=None, snapshot=None, config_sha256="a"*64,
                                     snapshot_manifest_sha256="b"*64)
    schema = default_contracts_dir() / "business.schema.json"
    config = SimpleNamespace(schema_path=schema, schema_sha256=hashlib.sha256(schema.read_bytes()).hexdigest())
    extractor.loader = SimpleNamespace(ready=True, config=config,
        generate=lambda *args, **kwargs: Generation(raw, "stop", 5, 5, .01, {}))
    return extractor


def payload():
    from vietdoc.contracts.compute import ComputeContracts
    scalars, _ = ComputeContracts().business_fields("receipt")
    return dict({key: None for key in scalars}, total_amount="80000", items=[])


@pytest.mark.parametrize("raw", [
    '{"total_amount":"80000","items":[]}',
    json.dumps(dict(payload(), total_amount=80000)),
    '```json\n'+json.dumps(payload())+'\n```',
    '{"total_amount":"1","total_amount":"2"}',
])
def test_schema_invalid_raw_is_never_repaired(raw):
    extractor = extractor_with_raw(raw)
    with pytest.raises(ComputeFailure, match="OUTPUT_INVALID"):
        extractor.extract(None, None, {"document_type":"receipt", "ocr_provenance":{}},
                          deadline=time.monotonic()+5)


def test_valid_model_payload_has_no_invented_confidence_or_source():
    extractor = extractor_with_raw(json.dumps(payload()))
    page = OcrPage(0, 100, 100, "fixture.v1", ())
    result = extractor.extract(page, None, {"document_type":"receipt", "ocr_provenance":{}},
                               deadline=time.monotonic()+5)
    assert result.payload == payload()
    assert all(f["confidence"] is None and f["ocr_score"] is None
               and f["raw_value"] is None and f["source_regions"] == [] for f in result.field_metadata)
    assert any(i["code"] == "FIELD_NOT_LOCATED" for i in result.issues)
    assert any(i["code"] == "MODEL_OUTPUT_REQUIRES_REVIEW" for i in result.issues)


def test_canonical_model_decimal_strings_are_not_locale_normalized():
    original = dict(payload(), total_amount="1.234", items=[{
        "description": "Fractional decimal", "quantity": "2.000", "unit": None,
        "unit_price": "0.617", "line_total": "1.234"}])
    extractor = extractor_with_raw(json.dumps(original))
    page = OcrPage(0, 100, 100, "fixture.v1", ())
    result = extractor.extract(page, None, {"document_type": "receipt", "ocr_provenance": {}},
                               deadline=time.monotonic()+5)
    assert result.payload == original
    assert not any(i["code"] == "FIELD_NOT_LOCATED" and i["paths"] == ["/items/0/quantity"]
                   for i in result.issues)


def test_unverified_local_selection_never_constructs_loader(monkeypatch):
    import vietdoc.ml.compute_extractor as module
    called = []
    monkeypatch.setattr(module, "QwenLoader", lambda *args: called.append(args))
    extractor = QwenComputeExtractor(None, config=Path("missing"), snapshot=Path("missing"),
        config_sha256="a"*64, snapshot_manifest_sha256="b"*64)
    with pytest.raises(ComputeFailure, match="MODEL_LOAD_FAILED"):
        extractor.load()
    assert called == [] and extractor.ready_reasons() == ["MODEL_LOAD_FAILED"]
    extractor.close()


def test_explicit_extractor_failure_closes_engine_and_loader(tmp_path, monkeypatch):
    import vietdoc.pipeline.composition as module
    from vietdoc.ml.release_manifest import Release, ReleaseFile
    events = []
    profile = dict(PROFILE, profile_version=2, extractor_version=VERSION)
    raw = json.dumps(profile).encode()
    (tmp_path / "pipeline.json").write_bytes(raw)
    release = Release("candidate", tmp_path, (ReleaseFile("pipeline.json", hashlib.sha256(raw).hexdigest(), len(raw)),))
    class Engine:
        def load(self): events.append("ocr-load")
        def close(self): events.append("ocr-close")
    class Extractor:
        version = VERSION
        def load(self):
            events.append("model-load")
            raise ComputeFailure("MODEL_LOAD_FAILED")
        def close(self): events.append("model-close")
    monkeypatch.setattr(module, "build_engine", lambda release: Engine())
    managed = ManagedPipeline("candidate", extractor_version=VERSION, extractor_factory=lambda release: Extractor())
    managed.startup({"candidate": release})
    assert managed.ready_reasons() == ["MODEL_LOAD_FAILED"]
    assert events == ["ocr-load", "model-load", "model-close", "ocr-close"]
    managed.close()
    assert len(events) == 4

@pytest.mark.parametrize("failure, expected", [("TIMEOUT", "COMPUTE_TIMEOUT"), ("OOM", "MODEL_OOM"),
                                              ("MODEL_BUSY", "AI_BUSY")])
def test_model_stage_error_mapping(failure, expected):
    from vietdoc.ml.qwen_config import MLFailure
    extractor = extractor_with_raw("{}")
    def generate(*args, **kwargs):
        raise MLFailure(failure, "generation")
    extractor.loader.generate = generate
    with pytest.raises(ComputeFailure, match=expected):
        extractor.extract(None, None, {"document_type":"receipt", "ocr_provenance":{}},
                          deadline=time.monotonic()+5)


def test_verified_pins_and_load_failure_close_runtime(tmp_path, monkeypatch):
    import vietdoc.ml.compute_extractor as module
    from vietdoc.ml.release_manifest import Release, ReleaseFile
    config = tmp_path / "config.yaml"
    config.write_bytes(b"fixture-only-config")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_bytes(b"fixture-only-base")
    pins = {"config_sha256":hashlib.sha256(config.read_bytes()).hexdigest(),
            "snapshot_manifest_sha256":hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest(),
            "run_manifest_sha256":None}
    raw = json.dumps(pins).encode()
    (tmp_path / "extractor.json").write_bytes(raw)
    release = Release("candidate", tmp_path, (ReleaseFile("extractor.json", hashlib.sha256(raw).hexdigest(), len(raw)),))
    events = []
    class Loader:
        def load(self):
            events.append("load")
            raise MemoryError()
        def close(self): events.append("close")
    monkeypatch.setattr(module, "load_config", lambda path: object())
    monkeypatch.setattr(module, "QwenLoader", lambda *args: Loader())
    extractor = QwenComputeExtractor(release, config=config, snapshot=snapshot, **pins)
    with pytest.raises(ComputeFailure, match="MODEL_LOAD_FAILED"):
        extractor.load()
    assert events == ["load", "close"] and extractor.loader is None
    events.clear()
    config.write_bytes(b"tampered")
    with pytest.raises(ComputeFailure, match="MODEL_LOAD_FAILED"):
        extractor.load()
    assert events == []


def test_adapter_rejects_a_different_training_config_even_with_matching_identity_pins(tmp_path, monkeypatch):
    import vietdoc.ml.training_g0 as training
    from vietdoc.ml.ocr_adapter import prompt_version
    from vietdoc.ml.qwen_config import load_config

    config_path = Path(__file__).resolve().parents[3] / "src/vietdoc/ml/configs/qwen-g0.yaml"
    config = load_config(config_path)
    snapshot = tmp_path / "base"
    snapshot.mkdir()
    (snapshot / "tokenizer.json").write_bytes(b"fixture-tokenizer")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run = {"inference_config_sha256": config.config_sha256, "pins": {
        "model_id": config.model_id, "model_revision": config.revision,
        "schema_sha256": config.schema_sha256, "serialization_version": config.serialization_version,
        "prompt_version": prompt_version(config.serialization_version),
        "tokenizer_sha256": hashlib.sha256(b"fixture-tokenizer").hexdigest(),
        "model_manifest_sha256": "b" * 64}}
    monkeypatch.setattr(training, "verify_checkpoint", lambda *a, **k:
                        {"adapter_only": True, "adapter_verified": True})
    extractor = QwenComputeExtractor(None, config=config_path, snapshot=snapshot,
        config_sha256="a" * 64, snapshot_manifest_sha256="b" * 64, run_dir=run_dir,
        run_manifest_sha256="c" * 64)
    path = run_dir / "run_manifest.json"
    path.write_text(json.dumps(run))
    extractor.pins["run_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    extractor._verify_adapter(config)
    run["inference_config_sha256"] = "e" * 64
    path.write_text(json.dumps(run))
    extractor.pins["run_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Unverified adapter selection"):
        extractor._verify_adapter(config)
