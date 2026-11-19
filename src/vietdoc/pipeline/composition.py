"""Explicit native B0 runtime composition. Never provisions or downloads models."""
import hashlib
import json
from threading import Lock

from vietdoc.contracts.compute import ComputeContracts
from vietdoc.ml.release_manifest import Release, ReleaseError
from vietdoc.pipeline.extraction.baseline import BASELINE_VERSION
from vietdoc.pipeline.normalization import POLICY_VERSION
from vietdoc.pipeline.service import B0Pipeline, ComputeFailure

PROFILE = dict(profile_version=1, extractor_version=BASELINE_VERSION,
               normalizer_version=POLICY_VERSION, ocr_artifact_version=1, model_root="ocr")


def checked_profile(release: Release):
    # Recheck verified bytes at use time; release volume must remain read-only.
    data = release.file("pipeline.json").read_bytes()
    entry = next(item for item in release.files if item.path == "pipeline.json")
    if (len(data) != entry.size_bytes or hashlib.sha256(data).hexdigest() != entry.sha256
            or len(data) > 16384):
        raise ReleaseError("Invalid pipeline profile")
    profile = json.loads(data)
    if profile != PROFILE or any(type(profile.get(key)) is not type(value) for key, value in PROFILE.items()):
        raise ReleaseError("Unsupported pipeline profile")


def build_engine(release: Release):
    from vietdoc.pipeline.ocr.paddle_adapter import MODELS, VietnameseOcrEngine
    # Every native model byte must also belong to the verified release manifest.
    for model, spec in MODELS.items():
        for name in spec["files"]:
            release.file(f"ocr/{model}_infer/{name}")
    return VietnameseOcrEngine(release.root / "ocr", artifact_version=1)


class ManagedPipeline:
    def __init__(self, manifest_id: str | None, contracts: ComputeContracts | None = None):
        self.manifest_id, self.contracts = manifest_id, contracts
        self._pipeline = None
        self._reason = "PIPELINE_MANIFEST_NOT_CONFIGURED" if not manifest_id else "MODEL_LOAD_FAILED"
        self._lifecycle = Lock()

    def startup(self, releases: dict[str, Release]):
        with self._lifecycle:
            if self._pipeline is not None or not self.manifest_id:
                return
            engine = None
            try:
                release = releases[self.manifest_id]
                checked_profile(release)
                engine = build_engine(release)
                engine.load()
                self._pipeline = B0Pipeline(release, engine, self.contracts)
                self._reason = None
            except (KeyError, ValueError, OSError) as error:
                code = getattr(error, "code", "MANIFEST_UNAVAILABLE")
                self._reason = code if code in {"MODEL_OOM", "MODEL_LOAD_FAILED", "MANIFEST_UNAVAILABLE"} else "MODEL_LOAD_FAILED"
            except Exception:
                self._reason = "MODEL_LOAD_FAILED"
            finally:
                if engine is not None and self._pipeline is None:
                    try:
                        engine.close()
                    except Exception:
                        self._reason = "MODEL_LOAD_FAILED"

    def ready_reasons(self):
        return self._pipeline.ready_reasons() if self._pipeline else [self._reason]

    def run(self, job):
        with self._lifecycle:
            if self._pipeline is None:
                raise ComputeFailure("AI_NOT_READY")
            return self._pipeline.run(job)

    def close(self):
        # A cancelled HTTP waiter does not release this lock while run is active.
        with self._lifecycle:
            if self._pipeline is not None:
                self._pipeline.engine.close()
                self._pipeline = None
            self._reason = "MODEL_LOAD_FAILED"
