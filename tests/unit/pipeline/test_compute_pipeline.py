"""Real decode/B0/writer, with a test-only OCR engine at the native boundary."""
from dataclasses import replace
import hashlib
from io import BytesIO
import json
import time
import uuid

from PIL import Image
import pytest

from vietdoc.contracts.compute import ComputeContracts
from vietdoc.contracts.ocr import OcrBlock, OcrPage
from vietdoc.ml.release_manifest import Release
from vietdoc.pipeline.service import ComputeInput


class FixtureEngine:
    ready = True
    def __init__(self):
        self.loaded = None
        self.failure = None
    def recognize(self, loaded, *, remaining_budget_ms):
        self.loaded = loaded
        assert remaining_budget_ms > 0
        if self.failure:
            raise self.failure
        return OcrPage(0, loaded.metadata.canonical.width, loaded.metadata.canonical.height,
                       "test-only.ocr.v1", (
            OcrBlock("label", "Tổng tiền", ((.1,.4),(.4,.4),(.4,.5),(.1,.5)), .9, None),
            OcrBlock("value", "80.000", ((.5,.4),(.8,.4),(.8,.5),(.5,.5)), .8, None)))


def image_bytes(format="PNG"):
    stream = BytesIO()
    with Image.new("RGB", (100,100), "white") as image:
        image.save(stream, format=format)
    return stream.getvalue()


def make_job(tmp_path, document_type="receipt", data=None):
    from vietdoc.pipeline.attempt_artifacts import reserve_attempt
    data = image_bytes() if data is None else data
    request = dict(contract_version=1, job_id=str(uuid.uuid4()), run_id=str(uuid.uuid4()),
                   attempt_id=str(uuid.uuid4()), document_type=document_type, schema_version=f"{document_type}.v1",
                   language="vi", input_sha256=hashlib.sha256(data).hexdigest(),
                   pipeline_manifest_id="test-b0", remaining_budget_ms=30000)
    release = Release("test-b0", tmp_path / "models", ())
    directory = reserve_attempt(tmp_path / "attempts", request["job_id"], request["attempt_id"])
    return ComputeInput(request, data, release, directory, time.monotonic() + 30)


@pytest.mark.parametrize("kind", ["receipt", "invoice"])
@pytest.mark.parametrize("format", ["PNG", "JPEG", "PDF"])
def test_bytes_to_verified_response_and_files(tmp_path, kind, format):
    from vietdoc.pipeline.service import B0Pipeline
    job = make_job(tmp_path, kind, image_bytes(format))
    engine = FixtureEngine()
    response = B0Pipeline(job.release, engine).run(job)
    ComputeContracts().check_response(job.request, response)
    assert response["result"]["payload"]["total_amount"] == "80000"
    assert response["result"]["payload"]["items"] == []
    assert response["result"]["job_id"] == job.request["job_id"]
    assert response["canonical_page"]["width"] == engine.loaded.metadata.canonical.width
    for artifact in response["artifacts"]:
        data = (job.attempt_dir / artifact["asset_key"].rsplit("/", 1)[1]).read_bytes()
        assert artifact["sha256"] == hashlib.sha256(data).hexdigest()
        assert artifact["size_bytes"] == len(data)
    ocr = json.loads((job.attempt_dir / "ocr.json").read_bytes())
    assert ocr["width"] == response["canonical_page"]["width"]
    diagnostics = json.loads((job.attempt_dir / "diagnostics.json").read_bytes())
    assert diagnostics["input_sha256"] == job.request["input_sha256"]
    assert diagnostics["actual_ocr_run"] is True  # engine was invoked; provider identity is explicit
    assert diagnostics["ocr_version"] == "test-only.ocr.v1"
    assert set(diagnostics["timings_ms"]) >= {"decode_ms", "ocr_ms", "extract_normalize_evidence_ms"}
    with pytest.raises(ValueError):
        engine.loaded.canonical.getpixel((0,0))


def test_deadline_before_decode_publishes_nothing(tmp_path):
    from vietdoc.pipeline.service import B0Pipeline, ComputeFailure
    job = make_job(tmp_path)
    job = replace(job, deadline=time.monotonic() - 1)
    engine = FixtureEngine()
    with pytest.raises(ComputeFailure) as error:
        B0Pipeline(job.release, engine).run(job)
    assert error.value.code == "COMPUTE_TIMEOUT"
    assert engine.loaded is None and list(job.attempt_dir.iterdir()) == []


def test_ocr_failure_cleans_images_and_next_request_can_run(tmp_path):
    from vietdoc.pipeline.ocr import OcrError
    from vietdoc.pipeline.service import B0Pipeline, ComputeFailure
    job = make_job(tmp_path)
    engine = FixtureEngine()
    engine.failure = OcrError("MODEL_OOM", "private native message")
    pipeline = B0Pipeline(job.release, engine)
    with pytest.raises(ComputeFailure) as error:
        pipeline.run(job)
    assert error.value.code == "MODEL_OOM" and "private" not in str(error.value)
    with pytest.raises(ValueError):
        engine.loaded.processed.getpixel((0,0))
    engine.failure = None
    assert pipeline.run(make_job(tmp_path))["result"]["payload"]["total_amount"] == "80000"


def test_partial_v2_activation_is_not_implicit(tmp_path):
    from vietdoc.pipeline.service import B0Pipeline, ComputeFailure
    job = make_job(tmp_path)
    class Version2(FixtureEngine):
        def recognize(self, loaded, **kwargs):
            return replace(super().recognize(loaded, **kwargs), artifact_version=2)
    with pytest.raises(ComputeFailure) as error:
        B0Pipeline(job.release, Version2()).run(job)
    assert error.value.code == "OUTPUT_INVALID"


def test_expired_after_extraction_cannot_publish(tmp_path, monkeypatch):
    import vietdoc.pipeline.service as service
    job = make_job(tmp_path)
    original = service.extract_baseline
    def expire(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(service.time, "monotonic", lambda: job.deadline + 1)
        return result
    monkeypatch.setattr(service, "extract_baseline", expire)
    with pytest.raises(service.ComputeFailure) as error:
        service.B0Pipeline(job.release, FixtureEngine()).run(job)
    assert error.value.code == "COMPUTE_TIMEOUT"
    assert not (job.attempt_dir / "canonical.png").exists()
