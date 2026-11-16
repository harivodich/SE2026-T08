"""Private compute port and actual accepted OCR → B0 → attempt artifacts path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from dataclasses import asdict
from io import BytesIO
import logging
import time

from vietdoc.contracts.compute import ComputeContracts
from vietdoc.entrypoints.api.output import encode_output
from vietdoc.ml.release_manifest import Release
from vietdoc.pipeline.attempt_artifacts import ArtifactError, AttemptWriter, check_deadline
from vietdoc.pipeline.extraction.baseline import BASELINE_VERSION, extract_baseline
from vietdoc.pipeline.extraction.evidence_adapter import BoundEvidence
from vietdoc.pipeline.extraction.ocr_input import BaselineError
from vietdoc.pipeline.normalization import POLICY_VERSION


@dataclass(frozen=True)
class ComputeInput:
    request: Mapping[str, Any]
    document: bytes
    release: Release
    attempt_dir: Path
    deadline: float  # time.monotonic() value; stages must stop before it


class ComputePipeline(Protocol):
    def ready_reasons(self) -> list[str]:
        """Empty when models are loaded and a compute slot can run."""
        ...

    def run(self, job: ComputeInput) -> dict[str, Any]:
        """Blocking compute; returns a compute-response object for this attempt."""
        ...


class ComputeFailure(ValueError):
    """Safe code only; provider exception details must not reach logs or wire."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class B0Pipeline:
    """One loaded engine, owned by the composition lifecycle; no model downloads."""
    def __init__(self, release: Release, engine, contracts: ComputeContracts | None = None):
        self.release, self.engine = release, engine
        self.contracts = contracts or ComputeContracts()

    def ready_reasons(self) -> list[str]:
        return [] if self.engine.ready else ["MODEL_LOAD_FAILED"]

    def run(self, job: ComputeInput) -> dict[str, Any]:
        from vietdoc.pipeline.ocr import OcrError, recognize_document
        from vietdoc.pipeline.preprocess import PreprocessError

        started = time.monotonic()
        timings = {}
        engine = self.engine

        class TimedOcr:
            def recognize(self, loaded, *, remaining_budget_ms):
                check_deadline(job.deadline)
                ocr_started = time.monotonic()
                timings["decode_ms"] = round((ocr_started - started) * 1000, 3)
                try:
                    return engine.recognize(loaded, remaining_budget_ms=min(
                        remaining_budget_ms, max(0, int((job.deadline - time.monotonic()) * 1000))))
                finally:
                    timings["ocr_ms"] = round((time.monotonic() - ocr_started) * 1000, 3)

        try:
            check_deadline(job.deadline)
            if job.release != self.release or job.request["pipeline_manifest_id"] != self.release.manifest_id:
                raise ComputeFailure("MANIFEST_UNAVAILABLE")
            self.contracts.validate("urn:vietdoc:compute-request:v1", dict(job.request))
            with recognize_document(job.document, TimedOcr(),
                                    remaining_budget_ms=max(0, int((job.deadline - time.monotonic()) * 1000)),
                                    expected_sha256=job.request["input_sha256"]) as stage:
                check_deadline(job.deadline)
                if stage.ocr.artifact_version != 1:
                    raise ComputeFailure("OUTPUT_INVALID")  # runtime v2 requires cross-role acceptance
                extraction_started = time.monotonic()
                result = extract_baseline(stage.ocr, job.request["document_type"], prepared=stage.loaded.metadata,
                                          evidence_matcher=BoundEvidence(stage.ocr, stage.loaded.metadata))
                check_deadline(job.deadline)
                timings["extract_normalize_evidence_ms"] = round((time.monotonic() - extraction_started) * 1000, 3)
                envelope = {key: job.request[key] for key in ("run_id", "job_id", "document_type", "schema_version", "language")}
                envelope.update(payload=result.payload, field_metadata=result.field_metadata, issues=result.issues,
                                provenance=dict(pipeline_manifest_id=self.release.manifest_id,
                                                ocr_version=stage.ocr.ocr_version, extractor_release_id=BASELINE_VERSION,
                                                normalizer_version=POLICY_VERSION))
                with BytesIO() as image:
                    stage.loaded.canonical.save(image, format="PNG")
                    canonical_bytes = image.getvalue()
                check_deadline(job.deadline)
                publication_started = time.monotonic()
                writer = AttemptWriter(job.attempt_dir, job.request["job_id"], job.request["attempt_id"], job.deadline)
                canonical = writer.write("canonical.png", canonical_bytes, "canonical_page", "image/png")
                writer.write("ocr.json", encode_output(stage.ocr.to_dict()), "ocr", "application/json")
                writer.write("prepared.json", encode_output(stage.loaded.metadata.to_dict()), "transform", "application/json")
                diagnostics = dict(artifact_version="vietdoc.compute-diagnostics.v1", actual_ocr_run=True,
                                   input_sha256=job.request["input_sha256"], ocr_version=stage.ocr.ocr_version,
                                   timings_ms=timings, provenance=envelope["provenance"],
                                   **{key: job.request[key] for key in ("job_id", "run_id", "attempt_id")},
                                   **asdict(result))
                writer.write("diagnostics.json", encode_output(diagnostics), "raw_prediction", "application/json")
                response = dict(contract_version=1, attempt_id=job.request["attempt_id"], result=envelope,
                                canonical_page=dict(page=0, width=stage.ocr.width, height=stage.ocr.height,
                                                    asset_key=canonical["asset_key"], sha256=canonical["sha256"]),
                                artifacts=writer.artifacts)
                writer.verify()
                timings["artifact_publication_verify_ms"] = round((time.monotonic() - publication_started) * 1000, 3)
                serialization_started = time.monotonic()
                encode_output(response)
                self.contracts.check_response(job.request, response)
                timings["serialization_validation_ms"] = round((time.monotonic() - serialization_started) * 1000, 3)
                check_deadline(job.deadline)
                logging.getLogger("vietdoc.ai_service").info("pipeline_stages", extra={
                    "attempt_id": job.request["attempt_id"], "stage_ms": timings,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3)})
                return response
        except (OcrError, PreprocessError, ArtifactError) as error:
            raise ComputeFailure(error.code) from None
        except MemoryError:
            raise ComputeFailure("MODEL_OOM") from None
        except OSError:
            raise ComputeFailure("AI_NOT_READY") from None
        except (BaselineError, ValueError, KeyError, TypeError):
            raise ComputeFailure("OUTPUT_INVALID") from None
        finally:
            for name, milliseconds in timings.items():
                logging.getLogger("vietdoc.ai_service").info("pipeline_stage", extra={
                    "attempt_id": job.request["attempt_id"], "stage": name, "duration_ms": milliseconds})

