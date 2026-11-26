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


def _read_profile(release: Release):
    # Recheck verified bytes at use time; release volume must remain read-only.
    data = release.file("pipeline.json").read_bytes()
    entry = next(item for item in release.files if item.path == "pipeline.json")
    if (len(data) != entry.size_bytes or hashlib.sha256(data).hexdigest() != entry.sha256
            or len(data) > 16384):
        raise ReleaseError("Invalid pipeline profile")
    return json.loads(data)


def checked_profile(release: Release, *, extractor_version=BASELINE_VERSION, ocr_artifact_version=1,
                    normalizer_version=POLICY_VERSION):
    profile = _read_profile(release)
    expected = dict(PROFILE)
    if extractor_version != BASELINE_VERSION or ocr_artifact_version != 1 or normalizer_version != POLICY_VERSION:
        expected.update(profile_version=2, extractor_version=extractor_version,
                        ocr_artifact_version=ocr_artifact_version, normalizer_version=normalizer_version)
    if (type(ocr_artifact_version) is not int or ocr_artifact_version not in (1, 2)
            or not isinstance(profile, dict) or profile != expected
            or any(type(profile.get(key)) is not type(value) for key, value in expected.items())):
        raise ReleaseError("Unsupported pipeline profile")
    return profile


def build_engine(release: Release):
    from vietdoc.pipeline.ocr.paddle_adapter import MODELS, VietnameseOcrEngine
    # Every native model byte must also belong to the verified release manifest.
    for model, spec in MODELS.items():
        for name in spec["files"]:
            release.file(f"ocr/{model}_infer/{name}")
    profile = _read_profile(release)
    return VietnameseOcrEngine(release.root / "ocr", artifact_version=profile["ocr_artifact_version"])


class ManagedPipeline:
    def __init__(self, manifest_id: str | None, contracts: ComputeContracts | None = None,
                 *, extractor_factory=None, extractor_version=BASELINE_VERSION, ocr_artifact_version=1,
                 normalizer_version=POLICY_VERSION):
        self.manifest_id, self.contracts = manifest_id, contracts
        self._pipeline = None
        self._reason = "PIPELINE_MANIFEST_NOT_CONFIGURED" if not manifest_id else "MODEL_LOAD_FAILED"
        self._lifecycle = Lock()
        self._extractor_factory = extractor_factory
        self._extractor_version = extractor_version
        self._ocr_artifact_version = ocr_artifact_version
        self._normalizer_version = normalizer_version

    def startup(self, releases: dict[str, Release]):
        with self._lifecycle:
            if self._pipeline is not None or not self.manifest_id:
                return
            engine = None
            extractor = None
            try:
                release = releases[self.manifest_id]
                checked_profile(release, extractor_version=self._extractor_version,
                                ocr_artifact_version=self._ocr_artifact_version,
                                normalizer_version=self._normalizer_version)
                if (self._extractor_factory is None) != (self._extractor_version == BASELINE_VERSION):
                    raise ReleaseError("Extractor selection requires an explicit matching factory")
                engine = build_engine(release)
                engine.load()
                if self._extractor_factory is not None:
                    extractor = self._extractor_factory(release)
                    if extractor.version != self._extractor_version:
                        raise ReleaseError("Extractor version mismatch")
                    if getattr(extractor, "normalizer_version", POLICY_VERSION) != self._normalizer_version:
                        raise ReleaseError("Normalizer selection mismatch")
                    extractor.load()
                    if extractor.ready_reasons():
                        raise ReleaseError("Extractor is not ready")
                self._pipeline = B0Pipeline(release, engine, self.contracts, extractor=extractor,
                                            ocr_artifact_version=self._ocr_artifact_version)
                self._reason = None
            except (KeyError, ValueError, OSError) as error:
                code = getattr(error, "code", "MANIFEST_UNAVAILABLE")
                self._reason = code if code in {"MODEL_OOM", "MODEL_LOAD_FAILED", "MANIFEST_UNAVAILABLE"} else "MODEL_LOAD_FAILED"
            except Exception:
                self._reason = "MODEL_LOAD_FAILED"
            finally:
                if extractor is not None and self._pipeline is None:
                    try:
                        extractor.close()
                    except Exception:
                        self._reason = "MODEL_LOAD_FAILED"
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
                active, self._pipeline = self._pipeline, None
                try:
                    if getattr(active, "extractor", None) is not None:
                        active.extractor.close()
                finally:
                    active.engine.close()
            self._reason = "MODEL_LOAD_FAILED"
