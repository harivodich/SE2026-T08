"""Verify an offline AI-1 OCR handoff directory and export an AI-2 consumer bundle.

Usage:
    python -m vietdoc.ml.ocr_handoff --handoff-root DIR --engine-manifest FILE --output-dir NEWDIR

This offline bridge validates AI-1 handoff artifacts (report.json, per-sample
run.json, canonical.png, ocr.json, prepared.json) and a caller-pinned local
release manifest before creating a new AI-2 consumer bundle directory containing
per-sample (ocr.json, prepared.json, provenance.json) and index.json.

Provenance four SHA-256 keys:
- input_sha256: caller-verified input declaration from coherent report.json and
  run.json (raw input and gold files are never read or rehashed).
- canonical_sha256: SHA-256 of verified canonical.png bytes (decoded RGB PNG
  within image pixel and byte caps, matching OcrPage and PreparedPage dimensions).
- engine_sha256: exact SHA-256 of the supplied --engine-manifest file bytes.
- profile_sha256: SHA-256 of canonical UTF-8 JSON
  json.dumps({"artifact_version": <int>, "ocr_version": <str>, "profile": report["profile"]},
             ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
  excluding timings, hardware and sample IDs.

Local AI-2 consumer bundle only; not a shared wire schema or pilot/model activation.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Any
import warnings

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.ml.qwen_config import MLFailure
from vietdoc.ml.release_manifest import ID_PATTERN, MANIFEST_VERSION, MAX_MANIFEST_BYTES
from vietdoc.pipeline.extraction.ocr_input import BaselineError, snapshot_page
from vietdoc.pipeline.ocr.handoff import HANDOFF_REPORT_VERSION

BUNDLE_VERSION = "vietdoc.ai2-ocr-handoff-bundle.v1"
MAX_JSON_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_SAMPLES = 20
_SAMPLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_PROFILE_KEYS = {"processed_long_edge", "pdf_dpi", "max_pixels", "budget_ms"}
_ALLOWED_PROFILE_KEYS = _REQUIRED_PROFILE_KEYS | {"max_file_bytes", "timeout_seconds"}
_CANONICAL_KEYS = {"width", "height", "sha256", "size_bytes", "rgb_pixel_sha256"}


class HandoffBridgeError(MLFailure):
    """Typed offline handoff bridge failure; never includes raw text or paths."""


def _is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return path.is_symlink()
    return (
        stat.S_ISLNK(info.st_mode)
        or path.is_symlink()
        or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    )


def _no_links(path: Path) -> None:
    current = Path(path)
    if not current.is_absolute():
        current = current.absolute()
    for part in (current, *current.parents):
        if _is_link(part):
            raise HandoffBridgeError("UNSAFE_PATH", "input")


def _safe_relative_posix(raw_path: object, *, stage: str = "input") -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path:
        raise HandoffBridgeError("UNSAFE_PATH", stage)
    if any(ord(c) < 32 or ord(c) == 127 for c in raw_path):
        raise HandoffBridgeError("UNSAFE_PATH", stage)
    relative = PurePosixPath(raw_path)
    if (
        relative.is_absolute()
        or "\\" in raw_path
        or ":" in raw_path
        or not relative.parts
        or any(part in ("", ".", "..") for part in raw_path.split("/"))
    ):
        raise HandoffBridgeError("UNSAFE_PATH", stage)
    return relative


def _contained_file(root: Path, raw_path: object, *, stage: str = "input") -> Path:
    relative = _safe_relative_posix(raw_path, stage=stage)
    _no_links(root)
    try:
        resolved_root = root.resolve()
    except OSError:
        raise HandoffBridgeError("UNSAFE_PATH", stage) from None
    current = root
    for part in relative.parts:
        current = current / part
        if _is_link(current):
            raise HandoffBridgeError("UNSAFE_PATH", stage)
    try:
        resolved_target = current.resolve()
    except OSError:
        raise HandoffBridgeError("UNSAFE_PATH", stage) from None
    if not resolved_target.is_relative_to(resolved_root):
        raise HandoffBridgeError("UNSAFE_PATH", stage)
    return current


def _canonical_json_bytes(value: Any, *, stage: str = "input") -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        return text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise HandoffBridgeError("JSON_INVALID", stage) from None


def _pretty_json_bytes(value: Any, *, stage: str = "export") -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        return text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise HandoffBridgeError("JSON_INVALID", stage) from None


def _parse_strict_json(raw: bytes, *, stage: str = "input", max_bytes: int = MAX_JSON_BYTES) -> Any:
    if not raw or len(raw) > max_bytes:
        raise HandoffBridgeError("JSON_INVALID", stage)

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for key, val in pairs:
            if key in record:
                raise ValueError("Duplicate JSON key")
            record[key] = val
        return record

    def reject_constant(_value: str) -> Any:
        raise ValueError("Nonfinite JSON constant")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite JSON float")
        return number

    try:
        decoded = raw.decode("utf-8", errors="strict")
        if decoded.startswith("\ufeff"):
            raise ValueError("Unexpected UTF-8 BOM")
        data = json.loads(
            decoded,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
        _canonical_json_bytes(data, stage=stage)
        return data
    except HandoffBridgeError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError, OverflowError):
        raise HandoffBridgeError("JSON_INVALID", stage) from None


def _read_json_file(path: Path, *, stage: str = "input", max_bytes: int = MAX_JSON_BYTES) -> tuple[Any, bytes, str]:
    _no_links(path)
    try:
        if not path.is_file():
            raise HandoffBridgeError("INPUT_MISSING", stage)
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except HandoffBridgeError:
        raise
    except OSError:
        raise HandoffBridgeError("INPUT_IO_ERROR", stage) from None
    data = _parse_strict_json(raw, stage=stage, max_bytes=max_bytes)
    return data, raw, hashlib.sha256(raw).hexdigest()


def compute_profile_sha256(profile: dict[str, Any], *, artifact_version: int, ocr_version: str) -> str:
    """Compute the deterministic profile_sha256 from report.profile, artifact_version, and ocr_version."""
    payload = {
        "artifact_version": artifact_version,
        "ocr_version": ocr_version,
        "profile": profile,
    }
    return hashlib.sha256(_canonical_json_bytes(payload, stage="profile")).hexdigest()


def _verify_engine_manifest(manifest_path: Path) -> dict[str, Any]:
    path = Path(manifest_path)
    _no_links(path)
    try:
        if not path.is_file():
            raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
        with path.open("rb") as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
    except HandoffBridgeError:
        raise
    except OSError:
        raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest") from None
    if not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
    try:
        data = _parse_strict_json(raw, stage="engine_manifest", max_bytes=MAX_MANIFEST_BYTES)
    except HandoffBridgeError:
        raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest") from None
    if not isinstance(data, dict) or set(data) != {"manifest_version", "pipeline_manifest_id", "files"}:
        raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
    version = data["manifest_version"]
    manifest_id = data["pipeline_manifest_id"]
    files = data["files"]
    if type(version) is not int or version != MANIFEST_VERSION:
        raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
    if not isinstance(manifest_id, str) or not ID_PATTERN.fullmatch(manifest_id):
        raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
    if not isinstance(files, list) or not files:
        raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")

    release_root = path.parent
    seen_paths: set[str] = set()
    seen_casefold: set[str] = set()
    normalized_files: list[dict[str, Any]] = []
    present_count = 0
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size_bytes"}:
            raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
        raw_path, file_sha, size = entry["path"], entry["sha256"], entry["size_bytes"]
        try:
            _safe_relative_posix(raw_path, stage="engine_manifest")
        except HandoffBridgeError:
            raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest") from None
        if (
            not isinstance(file_sha, str)
            or not _SHA256.fullmatch(file_sha)
            or type(size) is not int
            or size <= 0
            or raw_path in seen_paths
            or raw_path.casefold() in seen_casefold
        ):
            raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
        seen_paths.add(raw_path)
        seen_casefold.add(raw_path.casefold())
        try:
            candidate = _contained_file(release_root, raw_path, stage="engine_manifest")
        except HandoffBridgeError:
            raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest") from None
        if candidate.exists():
            if not candidate.is_file():
                raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
            try:
                if candidate.stat().st_size != size:
                    raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
                digest = hashlib.sha256()
                with candidate.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != file_sha:
                    raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest")
            except OSError:
                raise HandoffBridgeError("ENGINE_MANIFEST_INVALID", "engine_manifest") from None
            present_count += 1
        normalized_files.append({"path": raw_path, "sha256": file_sha, "size_bytes": size})

    return {
        "manifest_version": version,
        "pipeline_manifest_id": manifest_id,
        "engine_sha256": hashlib.sha256(raw).hexdigest(),
        "file_count": len(normalized_files),
        "files": normalized_files,
        "weights_verified": present_count == len(normalized_files),
    }


def _validate_profile(profile: object) -> tuple[dict[str, Any], int, int]:
    if not isinstance(profile, dict):
        raise HandoffBridgeError("REPORT_INVALID", "report")
    keys = set(profile)
    if not _REQUIRED_PROFILE_KEYS <= keys <= _ALLOWED_PROFILE_KEYS:
        raise HandoffBridgeError("REPORT_INVALID", "report")
    for key in ("processed_long_edge", "pdf_dpi", "max_pixels", "budget_ms"):
        val = profile[key]
        if type(val) is not int or val <= 0:
            raise HandoffBridgeError("REPORT_INVALID", "report")
    max_pixels = profile["max_pixels"]
    if max_pixels > MAX_IMAGE_PIXELS:
        raise HandoffBridgeError("REPORT_INVALID", "report")
    max_file_bytes = MAX_IMAGE_BYTES
    if "max_file_bytes" in profile:
        val = profile["max_file_bytes"]
        if type(val) is not int or not 0 < val <= MAX_IMAGE_BYTES:
            raise HandoffBridgeError("REPORT_INVALID", "report")
        max_file_bytes = val
    if "timeout_seconds" in profile:
        timeout = profile["timeout_seconds"]
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 180:
            raise HandoffBridgeError("REPORT_INVALID", "report")
    return dict(profile), max_pixels, max_file_bytes


def _verify_canonical_png(
    canonical_path: Path,
    canonical_meta: object,
    *,
    max_pixels: int,
    max_file_bytes: int,
) -> dict[str, Any]:
    from PIL import Image, UnidentifiedImageError

    if not isinstance(canonical_meta, dict):
        raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical")
    if not {"width", "height"} <= set(canonical_meta) <= _CANONICAL_KEYS:
        raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical")
    declared_w, declared_h = canonical_meta["width"], canonical_meta["height"]
    if type(declared_w) is not int or type(declared_h) is not int or declared_w <= 0 or declared_h <= 0:
        raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical")
    if declared_w * declared_h > max_pixels:
        raise HandoffBridgeError("PROFILE_EXCEEDED", "canonical")

    _no_links(canonical_path)
    try:
        if not canonical_path.is_file():
            raise HandoffBridgeError("INPUT_MISSING", "canonical")
        with canonical_path.open("rb") as stream:
            raw = stream.read(max_file_bytes + 1)
    except HandoffBridgeError:
        raise
    except OSError:
        raise HandoffBridgeError("INPUT_IO_ERROR", "canonical") from None
    if not raw or len(raw) > max_file_bytes or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical")

    actual_sha256 = hashlib.sha256(raw).hexdigest()
    actual_size = len(raw)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=("PNG",)) as image:
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise HandoffBridgeError("PROFILE_EXCEEDED", "canonical")
                if getattr(image, "n_frames", 1) != 1 or image.mode != "RGB":
                    raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical")
                image.load()
                actual_rgb_sha256 = hashlib.sha256(image.tobytes()).hexdigest()
    except HandoffBridgeError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HandoffBridgeError("PROFILE_EXCEEDED", "canonical") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical") from None

    if (width, height) != (declared_w, declared_h):
        raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical")

    recorded_sha = canonical_meta.get("sha256")
    source_hash_recorded = recorded_sha is not None
    if source_hash_recorded:
        if not isinstance(recorded_sha, str) or not _SHA256.fullmatch(recorded_sha) or recorded_sha != actual_sha256:
            raise HandoffBridgeError("CANONICAL_HASH_MISMATCH", "canonical")

    recorded_size = canonical_meta.get("size_bytes")
    if recorded_size is not None:
        if type(recorded_size) is not int or recorded_size != actual_size:
            raise HandoffBridgeError("CANONICAL_IMAGE_INVALID", "canonical")

    recorded_rgb_sha = canonical_meta.get("rgb_pixel_sha256")
    if recorded_rgb_sha is not None:
        if (
            not isinstance(recorded_rgb_sha, str)
            or not _SHA256.fullmatch(recorded_rgb_sha)
            or recorded_rgb_sha != actual_rgb_sha256
        ):
            raise HandoffBridgeError("CANONICAL_HASH_MISMATCH", "canonical")

    return {
        "width": width,
        "height": height,
        "sha256": actual_sha256,
        "size_bytes": actual_size,
        "rgb_pixel_sha256": actual_rgb_sha256,
        "source_hash_recorded": source_hash_recorded,
    }


def export_handoff(
    handoff_root: Path | str,
    engine_manifest: Path | str,
    output_dir: Path | str,
    *,
    sample_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate an AI-1 offline handoff and write a new AI-2 consumer bundle."""
    root = Path(handoff_root)
    output = Path(output_dir)
    _no_links(output)
    if output.exists() or _is_link(output):
        raise HandoffBridgeError("OUTPUT_EXISTS", "export")
    _no_links(root)
    if not root.is_dir():
        raise HandoffBridgeError("INPUT_MISSING", "input")

    engine_info = _verify_engine_manifest(Path(engine_manifest))
    engine_sha256 = engine_info["engine_sha256"]

    report_path = _contained_file(root, "report.json", stage="report")
    report, _, report_sha256 = _read_json_file(report_path, stage="report")
    if not isinstance(report, dict):
        raise HandoffBridgeError("REPORT_INVALID", "report")
    if report.get("report_version") != HANDOFF_REPORT_VERSION:
        raise HandoffBridgeError("REPORT_VERSION_UNSUPPORTED", "report")
    if report.get("run_status") != "completed" or report.get("abort_code") is not None:
        raise HandoffBridgeError("REPORT_STATUS_INVALID", "report")
    manifest_version = report.get("manifest_version")
    manifest_sha256 = report.get("manifest_sha256")
    if (
        not isinstance(manifest_version, str)
        or not manifest_version.strip()
        or not isinstance(manifest_sha256, str)
        or not _SHA256.fullmatch(manifest_sha256)
    ):
        raise HandoffBridgeError("REPORT_INVALID", "report")
    for optional_hash in ("font_sha256", "config_sha256"):
        val = report.get(optional_hash)
        if val is not None and (not isinstance(val, str) or not _SHA256.fullmatch(val)):
            raise HandoffBridgeError("REPORT_INVALID", "report")

    profile_dict, max_pixels, max_file_bytes = _validate_profile(report.get("profile"))

    samples = report.get("samples")
    counts = report.get("counts")
    if not isinstance(samples, list) or not 0 < len(samples) <= MAX_SAMPLES:
        raise HandoffBridgeError("REPORT_INVALID", "report")
    if not isinstance(counts, dict) or set(counts) != {"requested", "native_attempted", "ok", "failed", "not_run"}:
        raise HandoffBridgeError("REPORT_COUNTS_MISMATCH", "report")
    if any(type(v) is not int or v < 0 for v in counts.values()):
        raise HandoffBridgeError("REPORT_COUNTS_MISMATCH", "report")

    seen_ids: list[str] = []
    seen_casefold: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for sample in samples:
        if not isinstance(sample, dict):
            raise HandoffBridgeError("REPORT_INVALID", "report")
        sid = sample.get("sample_id")
        if not isinstance(sid, str) or not _SAMPLE_ID.fullmatch(sid):
            raise HandoffBridgeError("UNSAFE_PATH", "report")
        folded = sid.casefold()
        if sid in by_id or folded in seen_casefold:
            raise HandoffBridgeError("REPORT_INVALID", "report")
        seen_ids.append(sid)
        seen_casefold.add(folded)
        by_id[sid] = sample

        if sample.get("document_type") not in ("receipt", "invoice"):
            raise HandoffBridgeError("REPORT_INVALID", "report")
        if sample.get("status") not in ("ok", "failed", "not_run"):
            raise HandoffBridgeError("REPORT_INVALID", "report")
        expected_input = sample.get("expected_input_sha256")
        if not isinstance(expected_input, str) or not _SHA256.fullmatch(expected_input):
            raise HandoffBridgeError("REPORT_INVALID", "report")
        _safe_relative_posix(sample.get("input_declared_path"), stage="report")
        if type(sample.get("native_attempted")) is not bool:
            raise HandoffBridgeError("REPORT_INVALID", "report")
        if "engine_calls" in sample and (type(sample["engine_calls"]) is not int or sample["engine_calls"] < 0):
            raise HandoffBridgeError("REPORT_INVALID", "report")
        if "fixture_fallback" in sample and type(sample["fixture_fallback"]) is not bool:
            raise HandoffBridgeError("REPORT_INVALID", "report")

    actual_counts = {
        "requested": len(samples),
        "native_attempted": sum(1 for s in samples if s["native_attempted"]),
        "ok": sum(1 for s in samples if s["status"] == "ok"),
        "failed": sum(1 for s in samples if s["status"] == "failed"),
        "not_run": sum(1 for s in samples if s["status"] == "not_run"),
    }
    if counts != actual_counts:
        raise HandoffBridgeError("REPORT_COUNTS_MISMATCH", "report")
    if "observed_engine_calls" in report:
        observed_calls = report["observed_engine_calls"]
        if type(observed_calls) is not int or observed_calls != sum(s.get("engine_calls", 0) for s in samples):
            raise HandoffBridgeError("REPORT_COUNTS_MISMATCH", "report")

    if sample_ids is not None:
        if (
            not isinstance(sample_ids, (list, tuple))
            or not sample_ids
            or any(not isinstance(s, str) or not _SAMPLE_ID.fullmatch(s) for s in sample_ids)
            or len(sample_ids) != len(set(sample_ids))
            or set(sample_ids) - set(by_id)
        ):
            raise HandoffBridgeError("SELECTION_INVALID", "report")
        if any(by_id[s]["status"] != "ok" for s in sample_ids):
            raise HandoffBridgeError("SELECTION_INVALID", "report")
        selected_ids = set(sample_ids)
    else:
        selected_ids = {s["sample_id"] for s in samples if s["status"] == "ok"}

    if not selected_ids:
        raise HandoffBridgeError("NO_OK_SAMPLES", "report")

    exported_plans: list[tuple[str, bytes, bytes, bytes]] = []
    index_samples: dict[str, dict[str, Any]] = {}
    excluded_records: list[dict[str, Any]] = []
    observed_profiles: set[tuple[int, str, str]] = set()

    for sample in samples:
        sid = sample["sample_id"]
        status = sample["status"]
        sample_dir = root / sid
        if _is_link(sample_dir):
            raise HandoffBridgeError("UNSAFE_PATH", "run")
        run_path = _contained_file(root, f"{sid}/run.json", stage="run")

        if status != "ok":
            error_code = sample.get("error_code")
            stage_name = sample.get("stage")
            if (
                not isinstance(error_code, str)
                or not error_code.strip()
                or not isinstance(stage_name, str)
                or not stage_name.strip()
            ):
                raise HandoffBridgeError("REPORT_INVALID", "report")
            if run_path.exists() or _is_link(run_path):
                run_data, _, _ = _read_json_file(run_path, stage="run")
                if run_data != sample:
                    raise HandoffBridgeError("REPORT_RUN_MISMATCH", "run")
            elif sample.get("record_write_error") != "LOCAL_EXPORT_FAILED":
                raise HandoffBridgeError("REPORT_RUN_MISMATCH", "run")
            excluded_records.append(
                {
                    "sample_id": sid,
                    "document_type": sample["document_type"],
                    "status": status,
                    "stage": stage_name,
                    "reason": error_code,
                    "error_code": error_code,
                }
            )
            continue

        if "error_code" in sample or "record_write_error" in sample:
            raise HandoffBridgeError("REPORT_INVALID", "report")
        if not run_path.exists():
            raise HandoffBridgeError("REPORT_RUN_MISMATCH", "run")
        run_data, _, _ = _read_json_file(run_path, stage="run")
        if run_data != sample:
            raise HandoffBridgeError("REPORT_RUN_MISMATCH", "run")

        if sid not in selected_ids:
            excluded_records.append(
                {
                    "sample_id": sid,
                    "document_type": sample["document_type"],
                    "status": status,
                    "stage": sample.get("stage", "export"),
                    "reason": "NOT_SELECTED",
                    "error_code": None,
                }
            )
            continue

        input_sha256 = sample.get("input_sha256")
        if (
            not isinstance(input_sha256, str)
            or not _SHA256.fullmatch(input_sha256)
            or input_sha256 != sample["expected_input_sha256"]
        ):
            raise HandoffBridgeError("REPORT_RUN_MISMATCH", "report")

        artifact_paths = sample.get("artifact_paths")
        if artifact_paths is not None:
            if not isinstance(artifact_paths, dict) or not {"canonical.png", "ocr.json", "prepared.json"} <= set(artifact_paths):
                raise HandoffBridgeError("REPORT_INVALID", "report")
            for name, rel in artifact_paths.items():
                _safe_relative_posix(name, stage="report")
                _safe_relative_posix(rel, stage="report")
                if rel != f"{sid}/{name}":
                    raise HandoffBridgeError("UNSAFE_PATH", "report")
                _contained_file(root, rel, stage="report")

        canonical_path = _contained_file(root, f"{sid}/canonical.png", stage="canonical")
        canonical_info = _verify_canonical_png(
            canonical_path,
            sample.get("canonical"),
            max_pixels=max_pixels,
            max_file_bytes=max_file_bytes,
        )

        prepared_path = _contained_file(root, f"{sid}/prepared.json", stage="prepared")
        prepared_data, prepared_bytes, prepared_sha256 = _read_json_file(prepared_path, stage="prepared")
        try:
            prepared_page = PreparedPage.from_dict(prepared_data)
        except (ValueError, TypeError):
            raise HandoffBridgeError("PREPARED_INVALID", "prepared") from None
        if prepared_page.to_dict() != prepared_data or sample.get("prepared") != prepared_data:
            raise HandoffBridgeError("REPORT_RUN_MISMATCH", "prepared")
        if (prepared_page.canonical.width, prepared_page.canonical.height) != (
            canonical_info["width"],
            canonical_info["height"],
        ):
            raise HandoffBridgeError("PREPARED_INVALID", "prepared")
        if (
            prepared_page.canonical.width * prepared_page.canonical.height > max_pixels
            or prepared_page.processed.width * prepared_page.processed.height > max_pixels
        ):
            raise HandoffBridgeError("PROFILE_EXCEEDED", "prepared")
        source_prepared_sha = sample.get("prepared_sha256")
        if source_prepared_sha is not None:
            if not isinstance(source_prepared_sha, str) or source_prepared_sha != prepared_sha256:
                raise HandoffBridgeError("PREPARED_INVALID", "prepared")

        ocr_path = _contained_file(root, f"{sid}/ocr.json", stage="ocr")
        ocr_data, ocr_bytes, ocr_sha256 = _read_json_file(ocr_path, stage="ocr")
        try:
            ocr_page = OcrPage.from_dict(ocr_data)
            ocr_page.validate_against(prepared_page)
            snapshot_page(ocr_data, prepared_data)
        except (ValueError, TypeError, BaselineError) as err:
            code = "PROFILE_EXCEEDED" if isinstance(err, BaselineError) and err.code == "PROFILE_EXCEEDED" else "OCR_INVALID"
            raise HandoffBridgeError(code, "ocr") from None
        if ocr_page.to_dict() != ocr_data:
            raise HandoffBridgeError("OCR_INVALID", "ocr")
        if (ocr_page.width, ocr_page.height) != (canonical_info["width"], canonical_info["height"]):
            raise HandoffBridgeError("OCR_INVALID", "ocr")
        if (
            sample.get("ocr_version") != ocr_page.ocr_version
            or sample.get("artifact_version") != ocr_page.artifact_version
            or sample.get("recognition_status") != ocr_page.recognition_status
            or sample.get("review_flags") != list(ocr_page.review_flags)
            or sample.get("block_count") != len(ocr_page.blocks)
            or sample.get("unreadable_count") != len(ocr_page.unreadable_regions)
        ):
            raise HandoffBridgeError("REPORT_RUN_MISMATCH", "ocr")
        source_ocr_sha = sample.get("ocr_sha256")
        if source_ocr_sha is not None:
            if not isinstance(source_ocr_sha, str) or source_ocr_sha != ocr_sha256:
                raise HandoffBridgeError("OCR_INVALID", "ocr")

        profile_sha256 = compute_profile_sha256(
            profile_dict,
            artifact_version=ocr_page.artifact_version,
            ocr_version=ocr_page.ocr_version,
        )
        observed_profiles.add((ocr_page.artifact_version, ocr_page.ocr_version, profile_sha256))

        provenance = {
            "input_sha256": input_sha256,
            "canonical_sha256": canonical_info["sha256"],
            "engine_sha256": engine_sha256,
            "profile_sha256": profile_sha256,
        }
        provenance_bytes = _pretty_json_bytes(provenance, stage="export")
        provenance_sha256 = hashlib.sha256(provenance_bytes).hexdigest()

        exported_plans.append((sid, ocr_bytes, prepared_bytes, provenance_bytes))
        index_samples[sid] = {
            "sample_id": sid,
            "document_type": sample["document_type"],
            "status": "ok",
            "recognition_status": ocr_page.recognition_status,
            "artifact_version": ocr_page.artifact_version,
            "ocr_version": ocr_page.ocr_version,
            "preprocess_version": prepared_page.preprocess_version,
            "block_count": len(ocr_page.blocks),
            "unreadable_count": len(ocr_page.unreadable_regions),
            "review_flags": list(ocr_page.review_flags),
            "canonical": canonical_info,
            "paths": {
                "ocr": f"{sid}/ocr.json",
                "prepared": f"{sid}/prepared.json",
                "provenance": f"{sid}/provenance.json",
            },
            "hashes": {
                "ocr_sha256": ocr_sha256,
                "prepared_sha256": prepared_sha256,
                "provenance_sha256": provenance_sha256,
                "input_sha256": input_sha256,
                "canonical_sha256": canonical_info["sha256"],
                "engine_sha256": engine_sha256,
                "profile_sha256": profile_sha256,
            },
            "hash_origins": {
                "input_sha256": "declared_in_matched_report_and_run_not_rehashed_from_raw_input",
                "canonical_sha256": (
                    "verified_against_source_report_and_canonical_png_bytes"
                    if canonical_info["source_hash_recorded"]
                    else "computed_from_verified_canonical_png_bytes_no_source_hash_recorded"
                ),
                "ocr_sha256": (
                    "verified_against_source_report_and_ocr_json_bytes"
                    if source_ocr_sha is not None
                    else "computed_from_verified_handoff_ocr_json_bytes_not_upstream_origin_proof"
                ),
                "prepared_sha256": (
                    "verified_against_source_report_and_prepared_json_bytes"
                    if source_prepared_sha is not None
                    else "computed_from_verified_handoff_prepared_json_bytes_matched_to_report_snapshot"
                ),
            },
            "provenance": provenance,
        }

    if len(observed_profiles) != 1:
        raise HandoffBridgeError("PROFILE_MISMATCH", "report")
    common_artifact_version, common_ocr_version, common_profile_sha256 = next(iter(observed_profiles))

    index_payload: dict[str, Any] = {
        "bundle_version": BUNDLE_VERSION,
        "kind": "local AI2 OCR handoff consumer bundle; not shared wire schema or pilot/production approval",
        "shared_wire_schema": False,
        "pilot_approval": False,
        "production_active": False,
        "source_report_version": report["report_version"],
        "source_report_sha256": report_sha256,
        "source_manifest_version": manifest_version,
        "source_manifest_sha256": manifest_sha256,
        "engine_manifest": engine_info,
        "profile": {
            "profile": profile_dict,
            "artifact_version": common_artifact_version,
            "ocr_version": common_ocr_version,
            "profile_sha256": common_profile_sha256,
        },
        "counts": {
            "requested": counts["requested"],
            "exported": len(exported_plans),
            "excluded": len(excluded_records),
            "ok": counts["ok"],
            "failed": counts["failed"],
            "not_run": counts["not_run"],
        },
        "samples": index_samples,
        "excluded": excluded_records,
        "provenance_assurance": {
            "input_sha256": (
                "copied from coherent report.json and run.json caller-verified declaration; "
                "raw input bytes and gold were not read or rehashed by this bridge"
            ),
            "canonical_sha256": (
                "verified by decoding handoff canonical.png (RGB PNG within pixel/byte limits) "
                "and matching dimensions/hashes before export; canonical.png is not copied into output"
            ),
            "ocr_and_prepared_hashes": (
                "computed from verified handoff ocr.json and prepared.json bytes and recorded in this "
                "output inventory; new hashes record handoff snapshot state and do not independently "
                "prove upstream original OCR integrity"
            ),
            "engine_sha256": (
                "exact SHA-256 of supplied engine release manifest bytes with local release files verified"
                if engine_info["weights_verified"]
                else "exact SHA-256 of supplied engine release manifest bytes; listed weight files were not hashed or verified on disk"
            ),
            "profile_sha256": (
                "SHA-256 of canonical UTF-8 JSON for {'artifact_version', 'ocr_version', 'profile'} "
                "excluding timings, hardware and sample IDs"
            ),
        },
    }
    index_bytes = _pretty_json_bytes(index_payload, stage="export")

    created_root = False
    try:
        output.mkdir(parents=True, exist_ok=False)
        created_root = True
        for sid, ocr_bytes, prepared_bytes, provenance_bytes in exported_plans:
            sample_out = output / sid
            sample_out.mkdir(exist_ok=False)
            for filename, content in (
                ("ocr.json", ocr_bytes),
                ("prepared.json", prepared_bytes),
                ("provenance.json", provenance_bytes),
            ):
                with (sample_out / filename).open("xb") as stream:
                    stream.write(content)
        with (output / "index.json").open("xb") as stream:
            stream.write(index_bytes)
    except FileExistsError:
        if created_root:
            shutil.rmtree(output, ignore_errors=True)
        raise HandoffBridgeError("OUTPUT_EXISTS", "export") from None
    except OSError:
        if created_root:
            shutil.rmtree(output, ignore_errors=True)
        raise HandoffBridgeError("EXPORT_IO_ERROR", "export") from None

    return index_payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-root", type=Path, required=True)
    parser.add_argument("--engine-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-ids", nargs="+")
    args = parser.parse_args(argv)
    try:
        index = export_handoff(
            args.handoff_root,
            args.engine_manifest,
            args.output_dir,
            sample_ids=args.sample_ids,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "counts": index["counts"],
                    "weights_verified": index["engine_manifest"]["weights_verified"],
                    "production_active": False,
                }
            )
        )
        return 0
    except HandoffBridgeError as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": error.code,
                    "stage": error.stage,
                    "production_active": False,
                }
            )
        )
        return 2
    except Exception:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": "UNEXPECTED_FAILURE",
                    "stage": "export",
                    "production_active": False,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
