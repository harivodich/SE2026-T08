"""Offline dev comparison support. Inference inputs contain no annotations.

The host entrypoint supplies immutable run identities; scoring uses the existing
D3.2 evaluator and retains failed/missing records in its denominators.
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import struct
import sys
import tempfile
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from vietdoc.contracts.compute import ComputeContracts
from vietdoc.ml.ocr_adapter import business_schema, prompt_version
from vietdoc.ml.qwen_config import MLFailure, read_config_mapping
from vietdoc.ml.training_dataset import (
    _check_no_forbidden_ocr_keys,
    _contained_file,
    _read_strict_json,
    load_ocr_handoff_bundle,
)
from vietdoc.ml.training_g0 import G0TrainingConfig, verify_checkpoint
from vietdoc.pipeline.extraction.baseline import BASELINE_VERSION, extract_baseline
from vietdoc.pipeline.extraction.ocr_input import snapshot_page
from vietdoc.pipeline.extraction.output_parser import parse_model_output
from vietdoc.pipeline.normalization import POLICY_VERSION

VERSION = "vietdoc.offline-dev-comparison.v1"
_LOGGER = logging.getLogger(__name__)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write("\n")


def evaluator_training_hash() -> str:
    """Original source-tree pin algorithm used by the D22 training controller."""
    from vietdoc.evaluation import extended

    root = Path(extended.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(
            path.relative_to(root).as_posix().encode()
            + b"\0"
            + path.read_bytes()
            + b"\0"
        )
    return digest.hexdigest()


def select_dev(manifest_path: Path, expected_sha256: str) -> tuple[dict, list[dict]]:
    """Read metadata only; never dereference a train/final asset."""
    manifest, _, digest = _read_strict_json(manifest_path, max_bytes=8 * 1024 * 1024)
    if digest != expected_sha256:
        raise MLFailure("DATASET_MANIFEST_MISMATCH", "evaluation")
    samples = manifest.get("samples", [])
    ids = [s.get("sample_id") for s in samples]
    if (
        not samples
        or len(set(ids)) != len(ids)
        or any(not isinstance(sid, str) for sid in ids)
    ):
        raise MLFailure("DATASET_MEMBERSHIP_INVALID", "evaluation")
    dev = [s for s in samples if s.get("split") == "dev"]
    if not dev or any(
        s.get("document_type") not in ("receipt", "invoice") for s in dev
    ):
        raise MLFailure("DEV_POPULATION_INVALID", "evaluation")
    return manifest, dev


def verify_training_identity(
    training_root: Path,
    repo: Path,
    *,
    run_sha256: str,
    checkpoint_sha256: str,
    config_sha256: str,
    preflight_sha256: str,
) -> tuple[object, dict]:
    """Authenticate actual run/config/source before considering adapter attachment."""
    run_dir = training_root / "runs/full-epoch"
    if (
        sha(run_dir / "run_manifest.json") != run_sha256
        or sha(run_dir / "checkpoint/checkpoint_manifest.json") != checkpoint_sha256
        or sha(training_root / "g0-full-local.yaml") != config_sha256
        or sha(training_root / "preflight-report.json") != preflight_sha256
    ):
        raise MLFailure("ADAPTER_IDENTITY_MISMATCH", "evaluation")
    verified = verify_checkpoint(run_dir, verify_torch_weights=False)
    if not verified["adapter_verified"] or not verified["adapter_only"]:
        raise MLFailure("ADAPTER_IDENTITY_MISMATCH", "evaluation")
    run, _, _ = _read_strict_json(run_dir / "run_manifest.json")
    evidence, _, _ = _read_strict_json(training_root / "preflight-report.json")
    # Pin the implementation that produced the actual serialization/checkpoint.
    for rel, digest in evidence["source"]["files"].items():
        if rel.startswith("src/") and sha(_contained_file(repo, rel)) != digest:
            raise MLFailure("TRAIN_INFERENCE_SOURCE_MISMATCH", "evaluation")
    mapping, _ = read_config_mapping(training_root / "g0-full-local.yaml", repo)
    cfg = G0TrainingConfig.from_mapping(mapping, repo).to_inference_config()
    pins = run["pins"]
    expected = {
        "model_id": cfg.model_id,
        "model_revision": cfg.revision,
        "schema_sha256": cfg.schema_sha256,
        "serialization_version": cfg.serialization_version,
        "prompt_version": prompt_version(cfg.serialization_version),
    }
    if (
        any(pins.get(k) != v for k, v in expected.items())
        or cfg.config_sha256 != run["inference_config_sha256"]
        or evidence["serialization_sha256"] != pins["serialization_sha256"]
    ):
        raise MLFailure("ADAPTER_CONFIG_MISMATCH", "evaluation")
    adapter, _, _ = _read_strict_json(
        run_dir / "checkpoint/adapter/adapter_config.json"
    )
    base_ref = adapter.get("base_model_name_or_path", "")
    if (
        Path(base_ref).name != cfg.revision
        or adapter.get("revision") not in (None, cfg.revision)
        or adapter.get("peft_type") != "LORA"
        or adapter.get("task_type") != "CAUSAL_LM"
        or adapter.get("peft_version") != "0.21.2"
    ):
        raise MLFailure("ADAPTER_BASE_MISMATCH", "evaluation")
    return cfg, {
        "run": run,
        "checkpoint": verified,
        "config_file_sha256": config_sha256,
        "training_source_sha256": evidence["source"]["sha256"],
    }


def verify_model_identity(snapshot: Path, cfg, pins: dict, *, reprovision: Path | None = None,
                          reprovision_sha256: str | None = None) -> dict:
    from vietdoc.ml.model_provision import verify_snapshot

    verified = verify_snapshot(snapshot)
    if (
        verified["revision"] != cfg.revision
        or verified["model_id"] != cfg.model_id
        or sha(snapshot / "tokenizer.json") != pins["tokenizer_sha256"]
    ):
        raise MLFailure("ADAPTER_BASE_MISMATCH", "evaluation")
    current_manifest = sha(snapshot / "manifest.json")
    if current_manifest != pins["model_manifest_sha256"]:
        if reprovision is None or sha(reprovision) != reprovision_sha256:
            raise MLFailure("ADAPTER_BASE_MISMATCH", "evaluation")
        proof, _, _ = _read_strict_json(reprovision, stage="evaluation")
        required = {
            "version": "vietdoc.base-reprovision.v1",
            "model_id": cfg.model_id,
            "revision": cfg.revision,
            "training_model_manifest_sha256": pins["model_manifest_sha256"],
            "current_model_manifest_sha256": current_manifest,
            "tokenizer_sha256": pins["tokenizer_sha256"],
        }
        if any(proof.get(key) != value for key, value in required.items()):
            raise MLFailure("ADAPTER_BASE_MISMATCH", "evaluation")
        from vietdoc.ml import model_provision
        upstream = proof.get("upstream_metadata")
        expected = model_provision._metadata(upstream)
        verified_files = [model_provision._verify_file(snapshot, expected[name])
                          for name in model_provision.REQUIRED_FILES]
        if proof.get("verified_files") != verified_files:
            raise MLFailure("ADAPTER_BASE_MISMATCH", "evaluation")
        verified = dict(verified, reprovisioned=True, reprovision_sha256=reprovision_sha256,
                        training_model_manifest_sha256=pins["model_manifest_sha256"],
                        current_model_manifest_sha256=current_manifest,
                        identity_basis="pinned upstream revision and every required file byte hash; provisioning envelope changed")
    return verified


def _load_dev_bundle(bundle: Path, selected: set[str], pins: dict):
    """Freeze checked membership before reading payloads; never reload a mutable index."""
    index_path = _contained_file(bundle, "index.json", stage="evaluation")
    metadata, raw_index, index_sha = _read_strict_json(index_path, stage="evaluation")
    members = metadata.get("samples") if isinstance(metadata, dict) else None
    if not isinstance(members, dict) or not members:
        raise MLFailure("OCR_HANDOFF_INVALID", "evaluation")
    if set(members) - selected:
        raise MLFailure("NON_DEV_OCR_INPUT", "evaluation")
    with tempfile.TemporaryDirectory(prefix="vietdoc-dev-bundle-") as folder:
        frozen = Path(folder)
        (frozen / "index.json").write_bytes(raw_index)
        for sid, entry in members.items():
            paths = entry.get("paths") if isinstance(entry, dict) else None
            if not isinstance(paths, dict) or set(paths) != {"ocr", "prepared", "provenance"}:
                raise MLFailure("OCR_HANDOFF_INVALID", "evaluation")
            for relative in paths.values():
                source = _contained_file(bundle, relative, stage="evaluation")
                if source.relative_to(bundle).parts[0] != sid:
                    raise MLFailure("DEV_INPUT_IDENTITY_MISMATCH", "evaluation")
                _, raw, _ = _read_strict_json(source, stage="evaluation")
                target = frozen / source.relative_to(bundle)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        index = load_ocr_handoff_bundle(
            frozen,
            expected_engine_sha256=pins["ocr_engine_sha256"],
            expected_profile_sha256=pins["ocr_profile_sha256"],
        )
        if index.index_sha256 != index_sha:
            raise MLFailure("OCR_HANDOFF_HASH_MISMATCH", "evaluation")
        return index


def inference_inputs(dev: list[dict], bundle: Path, pins: dict) -> tuple[dict, dict]:
    """Project native OCR only. Gold, labels and renderer transcript are not read."""
    selected = {s["sample_id"]: s for s in dev}
    index = _load_dev_bundle(bundle, set(selected), pins)
    inputs = {}
    for sid, sample in index.samples.items():
        entry = selected[sid]
        if (
            sample.document_type != entry["document_type"]
            or sample.provenance["input_sha256"] != entry["assets"]["png"]["sha256"]
        ):
            raise MLFailure("DEV_INPUT_IDENTITY_MISMATCH", "evaluation")
        value = {
            "ocr": sample.ocr,
            "prepared": sample.prepared,
            "provenance": sample.provenance,
            "document_type": sample.document_type,
        }
        _check_no_forbidden_ocr_keys(value)
        inputs[sid] = value
    return inputs, {
        "ocr_index_sha256": index.index_sha256,
        "ocr_version": index.ocr_version,
        "preprocess_version": next(iter(index.samples.values())).preprocess_version,
        "engine_sha256": index.engine_sha256,
        "profile_sha256": index.profile_sha256,
    }


def normalize_output(raw: str, kind: str, cfg, *, finish_reason: str = "stop") -> dict:
    """One parser/normalizer for B0/M0/M1; raw validity is diagnostic only."""
    parsed = parse_model_output(
        raw, kind, ComputeContracts(cfg.schema_path.parent), finish_reason=finish_reason
    )
    raw_json = raw_schema = False
    try:

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result

        original = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
        raw.encode("utf-8", errors="strict")
        raw_json = True
        raw_schema = Draft202012Validator(business_schema(cfg, kind)).is_valid(original)
    except (ValueError, UnicodeError, RecursionError):
        pass
    return {
        "raw_output": raw,
        "raw_json_valid": raw_json,
        "raw_schema_valid": raw_schema,
        "normalized_schema_valid": parsed.status == "ok",
        "parse_status": parsed.status,
        "normalization_issues": list(parsed.issues),
        "payload": parsed.payload,
    }


def infer_method(
    method: str,
    dev: list[dict],
    inputs: dict,
    cfg,
    metadata: dict,
    output: Path,
    *,
    loader=None,
    timeout_seconds: float = 180,
    runtime_failure: str | None = None,
) -> dict:
    """Record exactly one result per selected ID, including input/runtime failures."""
    records, diagnostics = [], []
    for sample in dev:
        sid, kind = sample["sample_id"], sample["document_type"]
        started = time.monotonic()
        detail = {
            "sample_id": sid,
            "document_type": kind,
            "input_tokens": None,
            "output_tokens": None,
            "raw_output": None,
            "raw_json_valid": False,
            "raw_schema_valid": False,
            "normalized_schema_valid": False,
            "error": None,
        }
        record = {"sample_id": sid, "document_type": kind, "status": "failed"}
        try:
            if runtime_failure is not None:
                raise MLFailure(runtime_failure, "load")
            value = inputs.get(sid)
            if value is None:
                raise MLFailure("OCR_INPUT_MISSING", "input")
            _check_no_forbidden_ocr_keys(value)
            page, prepared, provenance = (
                value[k] for k in ("ocr", "prepared", "provenance")
            )
            observed = snapshot_page(page, prepared)
            if method == "B0":
                result = extract_baseline(page, kind, prepared=prepared)
                raw = json.dumps(result.payload, ensure_ascii=False, allow_nan=False)
                finish = "stop"
                detail["baseline_issues"] = result.issues
            else:
                generated = loader.generate(
                    page, prepared, provenance, kind, deadline=started + timeout_seconds
                )
                raw, finish = generated.raw, generated.finish_reason
                detail.update(
                    input_tokens=generated.input_tokens,
                    output_tokens=generated.output_tokens,
                    generation_seconds=generated.seconds,
                    provenance=generated.provenance,
                )
            normalized = normalize_output(raw, kind, cfg, finish_reason=finish)
            payload = normalized.pop("payload")
            detail.update(normalized, finish_reason=finish)
            if detail["normalized_schema_valid"]:
                record.update(
                    status="ok",
                    payload=payload,
                    ocr_text="\n".join(block.text for block in observed.blocks),
                )
            else:
                record["error"] = "OUTPUT_" + detail["parse_status"].upper()
        except Exception as error:  # noqa: BLE001 - isolate and account for every sample
            # A per-sample exception is observable failure, never dropped from scoring.
            record["error"] = getattr(error, "code", type(error).__name__)
            detail["error_stage"] = getattr(error, "stage", "inference")
        detail.update(seconds=time.monotonic() - started, error=record.get("error"))
        records.append(record)
        diagnostics.append(detail)
        _LOGGER.info("dev inference method=%s sample_id=%s status=%s error=%s seconds=%.3f",
                     method, sid, record["status"], record.get("error"), detail["seconds"])
    artifact = dict(
        metadata,
        artifact_version="vietdoc.predictions.v1",
        model_version=BASELINE_VERSION
        if method == "B0"
        else method + "@" + cfg.revision,
        candidate=method,
        normalizer_version=POLICY_VERSION,
        predictions=records,
    )
    output.mkdir(exist_ok=False)
    write_json(output / "predictions.json", artifact)
    write_json(
        output / "samples.json",
        {
            "version": VERSION,
            "predictions_sha256": sha(output / "predictions.json"),
            "samples": diagnostics,
        },
    )
    return artifact


def close_loader(loader) -> None:
    """Dedicated offline process cleanup between serial base model loads."""
    runtime = loader.runtime
    torch = runtime.torch if runtime is not None else sys.modules.get("torch")
    loader.close()
    gc.collect()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def load_dev_gold(
    repo: Path, manifest_path: Path, manifest: dict, dev: list[dict]
) -> list[dict]:
    """Validate only selected dev assets through the existing Data consumer."""
    from vietdoc.data.generator import integration
    from vietdoc.data.manifest import asset_path, read_json
    from vietdoc.evaluation.scalar_ocr import validate_labels

    integration.check_manifest(manifest)
    schema = read_json(repo / "specs/contracts/business.schema.json")
    samples = []
    for entry in dev:
        if entry["split"] != "dev":
            raise MLFailure("FINAL_ACCESS_FORBIDDEN", "evaluation")
        gold = integration.check_sample(repo, manifest_path, entry, manifest, schema)
        base = manifest_path.parent
        labels = read_json(asset_path(base, entry["assets"]["labels.json"]["path"]))
        png = asset_path(base, entry["assets"]["png"]["path"])
        with png.open("rb") as stream:
            dimensions = struct.unpack(">II", stream.read(24)[16:24])
        sample = dict(
            entry,
            gold=gold,
            labels=labels,
            transcript=asset_path(base, entry["assets"]["txt"]["path"]).read_text(
                encoding="utf-8"
            ),
            transcript_scope="full_page",
            transcript_order="renderer-draw-call-v1",
            canonical_sha256=entry["assets"]["png"]["sha256"],
            canonical_dimensions=dimensions,
            regions=read_json(
                asset_path(base, entry["assets"]["regions.json"]["path"])
            ),
        )
        validate_labels(sample)
        samples.append(sample)
    return samples


def evaluate_artifacts(
    samples: list[dict],
    artifacts: dict,
    *,
    expected_manifest_sha256: str,
    expected_ids: set[str],
) -> dict:
    from vietdoc.evaluation import extended

    reports = {}
    if {s["sample_id"] for s in samples} != expected_ids or any(
        s.get("split") != "dev" for s in samples
    ):
        raise MLFailure("DEV_POPULATION_INVALID", "evaluation")
    for method, artifact in artifacts.items():
        if artifact.get("dataset_manifest_sha256") != expected_manifest_sha256:
            raise MLFailure("PREDICTION_DATASET_MISMATCH", "evaluation")
        if any(r["sample_id"] not in expected_ids for r in artifact["predictions"]):
            raise MLFailure("NON_DEV_PREDICTION", "evaluation")
        reports[method] = extended.evaluate(samples, artifact)
    comparison = extended.compare(artifacts)
    # D3.2 compares public artifact pins. This experiment also requires identical
    # native OCR bytes, serializer and token budgets across candidates.
    for key in (
        "ocr_index_sha256",
        "schema_sha256",
        "serialization_version",
        "prompt_version",
        "serialization_sha256",
        "inference_config_sha256",
    ):
        values = {name: a.get(key) for name, a in artifacts.items()}
        if (
            any(not isinstance(v, str) or not v for v in values.values())
            or len(set(values.values())) != 1
        ):
            comparison["fair"] = False
            comparison["mismatches"].append({"pin": key, "values": values})
    return {
        "version": VERSION,
        "comparison": comparison,
        "reports": reports,
        "promotion": {
            "eligible": False,
            "production_active": False,
            "reasons": [
                "V1_NUMERIC_THRESHOLDS_NOT_ACCEPTED",
                "SMALL_SYNTHETIC_D22_PILOT_ONLY",
            ],
        },
        "unavailable_metrics": {
            "confidence_intervals": "not implemented by versioned evaluator",
            "calibrated_confidence": "no calibrated field confidence supplied",
            "night_weather_camera": "no such condition labels in synthetic D22 dev",
        },
    }
