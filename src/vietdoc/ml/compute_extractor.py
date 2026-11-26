"""Opt-in strict local Qwen consumer. Loading does not imply quality acceptance."""
import hashlib
import json

from vietdoc.ml.model_loading import QwenLoader
from vietdoc.ml.qwen_config import load_config
from vietdoc.ml.qwen_inference import QwenInference
from vietdoc.pipeline.extraction.baseline import BaselineResult
from vietdoc.pipeline.service import ComputeFailure

VERSION = "qwen3-strict-local.v1"
NORMALIZER_VERSION = "schema-canonical-decimal-preserved.v1"


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class QwenComputeExtractor:
    version = VERSION
    normalizer_version = NORMALIZER_VERSION

    def __init__(self, release, *, config, snapshot, config_sha256,
                 snapshot_manifest_sha256, run_dir=None, run_manifest_sha256=None):
        self.release, self.config_path, self.snapshot = release, config, snapshot
        self.run_dir = run_dir
        self.pins = {"config_sha256": config_sha256,
                         "snapshot_manifest_sha256": snapshot_manifest_sha256,
                         "run_manifest_sha256": run_manifest_sha256}
        self.loader = None

    def _verify_selection(self):
        entry = next(f for f in self.release.files if f.path == "extractor.json")
        raw = self.release.file("extractor.json").read_bytes()
        if (len(raw) > 4096 or len(raw) != entry.size_bytes
                or hashlib.sha256(raw).hexdigest() != entry.sha256
                or json.loads(raw) != self.pins
                or _sha(self.config_path) != self.pins["config_sha256"]
                or _sha(self.snapshot / "manifest.json") != self.pins["snapshot_manifest_sha256"]
                or (self.run_dir is None) != (self.pins["run_manifest_sha256"] is None)):
            raise ValueError("Unverified model selection")

    def _verify_adapter(self, config):
        from vietdoc.ml.ocr_adapter import prompt_version
        from vietdoc.ml.qwen_config import (
            derive_inference_config_for_training,
            read_config_mapping,
        )
        from vietdoc.ml.training_g0 import verify_checkpoint
        verified = verify_checkpoint(self.run_dir, verify_torch_weights=False)
        run = json.loads((self.run_dir / "run_manifest.json").read_bytes())
        expected = {"model_id": config.model_id, "model_revision": config.revision,
                        "schema_sha256": config.schema_sha256,
                        "serialization_version": config.serialization_version,
                        "prompt_version": prompt_version(config.serialization_version),
                        "tokenizer_sha256": _sha(self.snapshot / "tokenizer.json"),
                        "model_manifest_sha256": self.pins["snapshot_manifest_sha256"]}
        # Only the execution/training opt-in booleans may differ from the
        # non-executable training fingerprint. Budgets/template/device/profile
        # and every other config field remain bound to the actual run.
        mapping, repository_root = read_config_mapping(
            self.config_path, config.schema_path.parent.parent.parent)
        training_fingerprint = derive_inference_config_for_training(mapping, repository_root).config_sha256
        if (_sha(self.run_dir / "run_manifest.json") != self.pins["run_manifest_sha256"]
                or not verified["adapter_only"] or not verified["adapter_verified"]
                or run.get("inference_config_sha256") != training_fingerprint
                or any(run["pins"].get(k) != v for k, v in expected.items())):
            raise ValueError("Unverified adapter selection")

    def load(self):
        if self.loader is not None:
            return
        loader = None
        try:
            self._verify_selection()
            config = load_config(self.config_path)
            if self.run_dir is not None:
                self._verify_adapter(config)
            loader = QwenLoader(config, self.snapshot)
            loader.load()
            if self.run_dir is not None:
                self._verify_adapter(config)
                from peft import PeftModel
                loader.model = PeftModel.from_pretrained(
                    loader.model, str(self.run_dir / "checkpoint/adapter"),
                    is_trainable=False, local_files_only=True)
                loader.model.eval()
            self.loader = loader
        except Exception:  # noqa: BLE001 - native/provider details stay off the private wire
            if loader is not None:
                loader.close()
            raise ComputeFailure("MODEL_LOAD_FAILED") from None

    def close(self):
        if self.loader is not None:
            loader, self.loader = self.loader, None
            loader.close()

    def ready_reasons(self):
        return [] if self.loader is not None and self.loader.ready else ["MODEL_LOAD_FAILED"]

    def extract(self, page, prepared, request, *, deadline):
        if self.ready_reasons():
            raise ComputeFailure("AI_NOT_READY")
        result = QwenInference(self.loader).run(page, prepared, request["ocr_provenance"],
                                              request["document_type"], deadline=deadline)
        if result.error:
            code = {"TIMEOUT": "COMPUTE_TIMEOUT", "OOM": "MODEL_OOM",
                    "MODEL_BUSY": "AI_BUSY", "MODEL_NOT_READY": "AI_NOT_READY"}.get(
                        result.error, "OUTPUT_INVALID")
            raise ComputeFailure(code)
        metadata, states, issues = [], {}, []
        # The training target is already canonical business JSON. Locale OCR
        # normalization would reinterpret "1.234" as 1234 and reject "2.000"
        # quantities. Strict original-byte/schema checks have succeeded above.
        payload = json.loads(result.raw_output)
        paths = [(f"/{key}", value) for key, value in payload.items() if key != "items"]
        paths += [(f"/items/{i}/{key}", value) for i, item in enumerate(payload["items"])
                  for key, value in item.items()]
        for path, value in paths:
            flags = ["CONFIDENCE_UNCALIBRATED", "MODEL_VALUE_UNVERIFIED"]
            if page.unreadable_regions:
                flags.extend(["OCR_UNREADABLE_REGIONS", "SOURCE_OCR_INCOMPLETE"])
            if value is None:
                flags.append("FIELD_NOT_LOCATED")
                issues.append({"id": f"FIELD_NOT_LOCATED:{path}", "code": "FIELD_NOT_LOCATED",
                                   "severity": "warning", "paths": [path], "message": "Review missing value against source."})
            states[path] = "unknown" if value is None else "present"
            metadata.append({"path": path, "raw_value": None, "value_origin": "prediction", "source_regions": [],
                                 "ocr_score": None, "confidence": None, "confidence_method": None, "review_flags": flags})
        for code in ["MODEL_OUTPUT_REQUIRES_REVIEW"] + list(page.review_flags):
            issues.append({"id": f"{code}:/", "code": code, "severity": "warning", "paths": ["/"],
                               "message": "Unaccepted model candidate; source review required."})
        return BaselineResult(payload, {"model_provenance": result.provenance}, metadata, issues, states)
