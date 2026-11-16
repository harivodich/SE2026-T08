"""Runtime composition must fail closed, load once, and close after active work."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vietdoc.ml.release_manifest import load_release


def release_at(root, profile):
    root.mkdir()
    data = json.dumps(profile).encode()
    (root / "pipeline.json").write_bytes(data)
    (root / "manifest.json").write_text(json.dumps(dict(manifest_version=1, pipeline_manifest_id="b0",
        files=[dict(path="pipeline.json", sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))])))
    return load_release(root.parent, root.name)


def test_no_configured_manifest_does_not_load_engine():
    from vietdoc.pipeline.composition import ManagedPipeline
    pipeline = ManagedPipeline(None)
    pipeline.startup({})
    assert pipeline.ready_reasons() == ["PIPELINE_MANIFEST_NOT_CONFIGURED"]
    pipeline.close()


@pytest.mark.parametrize("profile", [{}, {"profile_version": 1, "model_root": "../outside"},
    {"profile_version": 1, "extractor_version": "vi-label-header-b0.v3", "normalizer_version": "vi-VND.v2",
     "ocr_artifact_version": 2, "model_root": "ocr"}])
def test_unaccepted_or_invalid_profile_is_not_ready(tmp_path, profile):
    from vietdoc.pipeline.composition import ManagedPipeline
    release = release_at(tmp_path / "b0", profile)
    pipeline = ManagedPipeline("b0")
    pipeline.startup({"b0": release})
    assert pipeline.ready_reasons() == ["MANIFEST_UNAVAILABLE"]


def test_model_load_failure_is_safe_and_closes_failed_engine(tmp_path, monkeypatch):
    import vietdoc.pipeline.composition as composition
    from vietdoc.pipeline.ocr import OcrError
    release = release_at(tmp_path / "b0", dict(profile_version=1, extractor_version="vi-label-header-b0.v3",
        normalizer_version="vi-VND.v2", ocr_artifact_version=1, model_root="ocr"))
    closed = []
    class BadEngine:
        def load(self):
            raise OcrError("MODEL_LOAD_FAILED", "secret/native/private/path")
        def close(self):
            closed.append(True)
    monkeypatch.setattr(composition, "build_engine", lambda release: BadEngine())
    pipeline = composition.ManagedPipeline("b0")
    pipeline.startup({"b0": release})
    assert pipeline.ready_reasons() == ["MODEL_LOAD_FAILED"]
    assert closed == [True]


def test_loaded_engine_is_reused_and_closed_once(tmp_path, monkeypatch):
    import vietdoc.pipeline.composition as composition
    release = release_at(tmp_path / "b0", dict(profile_version=1, extractor_version="vi-label-header-b0.v3",
        normalizer_version="vi-VND.v2", ocr_artifact_version=1, model_root="ocr"))
    events = []
    class Engine:
        ready = True
        def load(self): events.append("load")
        def close(self): events.append("close")
    monkeypatch.setattr(composition, "build_engine", lambda release: Engine())
    pipeline = composition.ManagedPipeline("b0")
    pipeline.startup({"b0": release})
    pipeline.startup({"b0": release})
    assert pipeline.ready_reasons() == []
    pipeline.close()
    pipeline.close()
    assert events == ["load", "close"]


def test_shutdown_waits_for_active_native_work(monkeypatch):
    import threading
    from vietdoc.pipeline.composition import ManagedPipeline
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    class Active:
        engine = SimpleNamespace(close=closed.set)
        def run(self, job):
            entered.set()
            assert release.wait(5)
            return {"finished": True}
    pipeline = ManagedPipeline("b0")
    pipeline._pipeline = Active()
    worker = threading.Thread(target=lambda: pipeline.run(None))
    closer = threading.Thread(target=pipeline.close)
    worker.start()
    assert entered.wait(5)
    closer.start()
    try:
        assert not closed.wait(.05)
    finally:
        release.set()
        worker.join(5)
        closer.join(5)
    assert closed.is_set()
