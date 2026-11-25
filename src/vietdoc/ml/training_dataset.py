"""Offline AI-2 training reader, record adapter, four-state policy, and collator.

Joins a verified AI-2 OCR handoff consumer bundle (`vietdoc.ai2-ocr-handoff-bundle.v1`)
with typed Data records by `sample_id`. Enforces exact input/canonical/engine/profile
provenance, document type, strict business schema validation, four-state label
distinction (`present`/`absent`/`obscured`/`unlabeled`), leakage and final-split
rejection, and train/inference prompt parity via `vietdoc.ml.ocr_adapter.build_prompt`.

No model frameworks, downloads, serving activation, or gold-transcript OCR inputs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Literal

from jsonschema import Draft202012Validator

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.data.adapters.labels import (
    FieldLabel,
    FieldLabels,
    Status,
    VERSION as LABEL_ADAPTER_VERSION,
    field_labels as validate_field_labels,
)
from vietdoc.data.splits import assert_disjoint
from vietdoc.ml.ocr_adapter import (
    OcrPrompt,
    build_prompt,
    business_schema,
    prompt_version,
)
from vietdoc.ml.ocr_handoff import BUNDLE_VERSION, compute_profile_sha256
from vietdoc.ml.qwen_config import MLFailure, QwenConfig
from vietdoc.pipeline.extraction.ocr_input import BaselineError, snapshot_page

DATASET_ADAPTER_VERSION = "vietdoc.ai2-training-dataset.v1"
TARGET_SERIALIZATION_VERSION = "vietdoc.business-target-json.v1"
FOUR_STATES: tuple[Status, ...] = ("present", "absent", "obscured", "unlabeled")
ALLOWED_TRAINING_SPLITS: tuple[str, ...] = ("train", "dev")
MAX_JSON_BYTES = 1024 * 1024
LABEL_IGNORE_INDEX = -100

_SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROVENANCE_KEYS = frozenset(("input_sha256", "canonical_sha256", "engine_sha256", "profile_sha256"))
_FORBIDDEN_OCR_KEYS = frozenset(("gold", "gold_transcript", "transcript", "labels", "label_statuses"))
_RECEIPT_KEY_ORDER = (
    "merchant_name",
    "merchant_address",
    "transaction_date",
    "transaction_time",
    "total_amount",
    "items",
)
_INVOICE_KEY_ORDER = (
    "invoice_number",
    "issue_date",
    "seller_name",
    "buyer_name",
    "subtotal",
    "tax_amount",
    "discount_amount",
    "total_amount",
    "items",
)
_ITEM_KEY_ORDER = ("description", "quantity", "unit", "unit_price", "line_total")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _is_sample_id(value: object) -> bool:
    return isinstance(value, str) and bool(_SAMPLE_ID_RE.fullmatch(value))


def _is_nonblank_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


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


def _no_links(path: Path, *, stage: str = "dataset") -> None:
    current = Path(path)
    if not current.is_absolute():
        current = current.absolute()
    for part in (current, *current.parents):
        if _is_link(part):
            raise MLFailure("UNSAFE_PATH", stage)


def _safe_relative_posix(raw_path: object, *, stage: str = "dataset") -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path:
        raise MLFailure("UNSAFE_PATH", stage)
    if any(ord(c) < 32 or ord(c) == 127 for c in raw_path):
        raise MLFailure("UNSAFE_PATH", stage)
    rel = PurePosixPath(raw_path)
    if (
        rel.is_absolute()
        or "\\" in raw_path
        or ":" in raw_path
        or not rel.parts
        or any(part in ("", ".", "..") for part in raw_path.split("/"))
    ):
        raise MLFailure("UNSAFE_PATH", stage)
    return rel


def _contained_file(root: Path, raw_path: object, *, stage: str = "dataset") -> Path:
    rel = _safe_relative_posix(raw_path, stage=stage)
    _no_links(root, stage=stage)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        raise MLFailure("UNSAFE_PATH", stage) from None
    current = root
    for part in rel.parts:
        current = current / part
        if _is_link(current):
            raise MLFailure("UNSAFE_PATH", stage)
    try:
        resolved_target = current.resolve(strict=True)
    except OSError:
        raise MLFailure("INPUT_MISSING", stage) from None
    if not resolved_target.is_relative_to(resolved_root) or not resolved_target.is_file():
        raise MLFailure("UNSAFE_PATH", stage)
    return current


def _canonical_json_bytes(value: Any, *, stage: str = "dataset") -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        return text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise MLFailure("JSON_INVALID", stage) from None


def _read_strict_json(path: Path, *, stage: str = "dataset", max_bytes: int = MAX_JSON_BYTES) -> tuple[Any, bytes, str]:
    _no_links(path, stage=stage)
    try:
        if not path.is_file():
            raise MLFailure("INPUT_MISSING", stage)
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except MLFailure:
        raise
    except OSError:
        raise MLFailure("INPUT_IO_ERROR", stage) from None
    if not raw or len(raw) > max_bytes:
        raise MLFailure("JSON_INVALID", stage)

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, val in pairs:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = val
        return out

    def reject_constant(_value: str) -> Any:
        raise ValueError("Nonfinite constant")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite float")
        return number

    try:
        decoded = raw.decode("utf-8", errors="strict")
        if decoded.startswith("\ufeff"):
            raise ValueError("UTF-8 BOM rejected")
        parsed = json.loads(
            decoded,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
        _canonical_json_bytes(parsed, stage=stage)
    except MLFailure:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError, OverflowError):
        raise MLFailure("JSON_INVALID", stage) from None
    return parsed, raw, hashlib.sha256(raw).hexdigest()


def _check_no_forbidden_ocr_keys(value: Any, *, stage: str = "dataset") -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if isinstance(key, str) and key in _FORBIDDEN_OCR_KEYS:
                    raise MLFailure("GOLD_IN_OCR_INPUT", stage)
                pending.append(item)
        elif isinstance(current, list):
            pending.extend(current)


def _gold_leaves(gold: Mapping[str, Any]) -> dict[str, str | None]:
    if not isinstance(gold, Mapping) or not isinstance(gold.get("items"), list):
        raise MLFailure("GOLD_INVALID", "dataset")
    leaves: dict[str, str | None] = {f"/{key}": val for key, val in gold.items() if key != "items"}
    for idx, row in enumerate(gold["items"]):
        if not isinstance(row, Mapping):
            raise MLFailure("GOLD_INVALID", "dataset")
        for key, val in row.items():
            leaves[f"/items/{idx}/{key}"] = val
    return leaves


def _validate_field_labels_obj(gold: Mapping[str, Any], labels: FieldLabels | Mapping[str, Any]) -> FieldLabels:
    if isinstance(labels, FieldLabels):
        if labels.version != LABEL_ADAPTER_VERSION:
            raise MLFailure("LABEL_VERSION_INVALID", "dataset")
        expected_leaves = _gold_leaves(gold)
        seen: dict[str, FieldLabel] = {}
        for entry in labels.fields:
            if not isinstance(entry, FieldLabel):
                raise MLFailure("LABEL_STATUS_INVALID", "dataset")
            if entry.pointer in seen or entry.pointer not in expected_leaves:
                raise MLFailure("LABEL_COVERAGE_MISMATCH", "dataset")
            if entry.status not in FOUR_STATES:
                raise MLFailure("LABEL_STATUS_INVALID", "dataset")
            leaf_value = expected_leaves[entry.pointer]
            if entry.value != leaf_value:
                raise MLFailure("LABEL_VALUE_MISMATCH", "dataset")
            if (entry.status == "present") != (leaf_value is not None):
                raise MLFailure("LABEL_STATUS_MISMATCH", "dataset")
            seen[entry.pointer] = entry
        if set(seen) != set(expected_leaves):
            raise MLFailure("LABEL_COVERAGE_MISMATCH", "dataset")
        ordered = tuple(seen[pointer] for pointer in sorted(seen))
        return FieldLabels(labels.version, ordered)
    if isinstance(labels, Mapping) and set(labels) == {"version", "fields"}:
        # `vietdoc.training-records.v1` serializes the validated adapter as a
        # versioned list of {pointer,value,status}; accept that handoff shape
        # without weakening the stricter labels.json boundary below.
        version = labels.get("version")
        fields = labels.get("fields")
        if version != LABEL_ADAPTER_VERSION or not isinstance(fields, list):
            raise MLFailure("LABEL_VERSION_INVALID", "dataset")
        try:
            parsed = FieldLabels(
                version,
                tuple(
                    FieldLabel(item["pointer"], item["value"], item["status"])
                    for item in fields
                    if isinstance(item, Mapping)
                    and set(item) == {"pointer", "value", "status"}
                ),
            )
        except (KeyError, TypeError):
            raise MLFailure("LABEL_STATUS_INVALID", "dataset") from None
        if len(parsed.fields) != len(fields):
            raise MLFailure("LABEL_STATUS_INVALID", "dataset")
        return _validate_field_labels_obj(gold, parsed)
    if isinstance(labels, Mapping):
        try:
            return validate_field_labels(dict(gold), dict(labels))
        except ValueError:
            raise MLFailure("LABEL_STATUS_INVALID", "dataset") from None
    raise MLFailure("LABEL_STATUS_INVALID", "dataset")


def serialize_business_target(gold: Mapping[str, Any], document_type: str) -> str:
    """Serialize validated business gold in deterministic schema key order."""
    if document_type == "receipt":
        key_order = _RECEIPT_KEY_ORDER
    elif document_type == "invoice":
        key_order = _INVOICE_KEY_ORDER
    else:
        raise MLFailure("DOCUMENT_TYPE_INVALID", "dataset")
    if set(gold) != set(key_order) or not isinstance(gold.get("items"), list):
        raise MLFailure("GOLD_SCHEMA_INVALID", "dataset")
    ordered_items = []
    for row in gold["items"]:
        if not isinstance(row, Mapping) or set(row) != set(_ITEM_KEY_ORDER):
            raise MLFailure("GOLD_SCHEMA_INVALID", "dataset")
        ordered_items.append({key: row[key] for key in _ITEM_KEY_ORDER})
    ordered: dict[str, Any] = {}
    for key in key_order:
        ordered[key] = ordered_items if key == "items" else gold[key]
    try:
        encoded = json.dumps(ordered, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        encoded.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise MLFailure("GOLD_SCHEMA_INVALID", "dataset") from None
    return encoded


@dataclass(frozen=True)
class OcrHandoffSample:
    """One verified sample from an AI-2 OCR handoff consumer bundle."""

    sample_id: str
    document_type: Literal["receipt", "invoice"]
    ocr: dict[str, Any]
    prepared: dict[str, Any]
    provenance: dict[str, str]
    ocr_sha256: str
    prepared_sha256: str
    provenance_sha256: str
    artifact_version: int
    ocr_version: str
    preprocess_version: str
    recognition_status: str
    review_flags: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedOcrHandoffIndex:
    """Verified in-memory projection of an AI-2 OCR handoff bundle."""

    bundle_version: str
    index_sha256: str
    source_manifest_version: str
    source_manifest_sha256: str
    engine_sha256: str
    profile_sha256: str
    profile: dict[str, Any]
    artifact_version: int
    ocr_version: str
    samples: Mapping[str, OcrHandoffSample]


@dataclass(frozen=True)
class DataTrainingRecord:
    """Typed Data sample record paired with gold and explicit four-state labels."""

    sample_id: str
    base_id: str
    family_id: str
    source_group: str
    split: Literal["train", "dev", "final"]
    document_type: Literal["receipt", "invoice"]
    input_sha256: str
    gold: dict[str, Any]
    labels: FieldLabels | dict[str, Any]
    canonical_sha256: str | None = None
    assignment_group: str | None = None
    content_sha256: str | None = None
    population_id: str | None = None
    dataset_manifest_sha256: str | None = None


@dataclass(frozen=True)
class JoinedTrainingRecord:
    """Provenance-verified OCR + Data record eligible for full-JSON supervision."""

    sample_id: str
    base_id: str
    family_id: str
    source_group: str
    assignment_group: str | None
    split: Literal["train", "dev"]
    document_type: Literal["receipt", "invoice"]
    ocr: dict[str, Any]
    prepared: dict[str, Any]
    provenance: dict[str, str]
    gold: dict[str, Any]
    target_json: str
    field_labels: FieldLabels
    status_counts: dict[str, int]
    full_json_eligible: bool
    gold_sha256: str
    labels_sha256: str


@dataclass(frozen=True)
class ExcludedTrainingRecord:
    """Explicitly excluded sample (obscured/unlabeled fields), never silently dropped."""

    sample_id: str
    base_id: str
    family_id: str
    source_group: str
    split: Literal["train", "dev"]
    document_type: Literal["receipt", "invoice"]
    reason: str
    status_counts: dict[str, int]
    obscured_pointers: tuple[str, ...]
    unlabeled_pointers: tuple[str, ...]


@dataclass(frozen=True)
class TrainingDataset:
    """Verified joined dataset with explicit four-state accounting and lineage hashes."""

    adapter_version: str
    split: Literal["train", "dev"]
    population_id: str | None
    source_manifest_sha256: str
    ocr_bundle_version: str
    ocr_index_sha256: str
    engine_sha256: str
    profile_sha256: str
    schema_sha256: str
    serialization_version: str
    target_serialization_version: str
    prompt_version: str
    label_adapter_version: str
    sample_membership_sha256: str
    serialization_sha256: str
    examples: tuple[JoinedTrainingRecord, ...]
    excluded: tuple[ExcludedTrainingRecord, ...]
    status_totals: dict[str, int]
    counts: dict[str, int]


@dataclass(frozen=True)
class CollatedBatch:
    """Tokenized, right-padded batch with prompt/OCR/pad tokens masked to -100."""

    sample_ids: tuple[str, ...]
    document_types: tuple[str, ...]
    input_ids: tuple[tuple[int, ...], ...]
    attention_mask: tuple[tuple[int, ...], ...]
    labels: tuple[tuple[int, ...], ...]
    prompt_lengths: tuple[int, ...]
    target_lengths: tuple[int, ...]
    pad_token_id: int
    eos_token_id: int
    label_ignore_index: int
    prompt_sha256s: tuple[str, ...]
    serialization_sha256: str


def data_record_from_sample(
    sample: Mapping[str, Any],
    gold: Mapping[str, Any],
    labels: FieldLabels | Mapping[str, Any],
    *,
    canonical_sha256: str | None = None,
    population_id: str | None = None,
    dataset_manifest_sha256: str | None = None,
) -> DataTrainingRecord:
    """Adapt a Data manifest sample + gold + labels into a typed DataTrainingRecord."""
    if not isinstance(sample, Mapping):
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    assets = sample.get("assets")
    png = assets.get("png") if isinstance(assets, Mapping) else None
    input_sha = png.get("sha256") if isinstance(png, Mapping) else None
    try:
        return DataTrainingRecord(
            sample_id=sample["sample_id"],
            base_id=sample["base_id"],
            family_id=sample["family_id"],
            source_group=sample["source_group"],
            split=sample["split"],
            document_type=sample["document_type"],
            input_sha256=input_sha,
            gold=dict(gold) if isinstance(gold, Mapping) else gold,  # type: ignore[arg-type]
            labels=labels if isinstance(labels, FieldLabels) else dict(labels),  # type: ignore[arg-type]
            canonical_sha256=canonical_sha256,
            assignment_group=sample.get("assignment_group"),
            content_sha256=sample.get("content_sha256"),
            population_id=population_id or sample.get("population_id"),
            dataset_manifest_sha256=dataset_manifest_sha256,
        )
    except KeyError:
        raise MLFailure("DATA_RECORD_INVALID", "dataset") from None


def load_ocr_handoff_bundle(
    bundle_dir: Path | str,
    *,
    expected_engine_sha256: str | None = None,
    expected_profile_sha256: str | None = None,
    expected_source_manifest_sha256: str | None = None,
) -> VerifiedOcrHandoffIndex:
    """Verify an exported AI-2 OCR handoff directory before any training join."""
    root = Path(bundle_dir)
    _no_links(root, stage="ocr_handoff")
    if not root.is_dir():
        raise MLFailure("OCR_HANDOFF_MISSING", "ocr_handoff")

    index_path = _contained_file(root, "index.json", stage="ocr_handoff")
    index, _, index_sha256 = _read_strict_json(index_path, stage="ocr_handoff")
    if not isinstance(index, dict) or index.get("bundle_version") != BUNDLE_VERSION:
        raise MLFailure("OCR_HANDOFF_INVALID", "ocr_handoff")

    source_manifest_version = index.get("source_manifest_version")
    source_manifest_sha256 = index.get("source_manifest_sha256")
    if not _is_nonblank_str(source_manifest_version) or not _is_sha256(source_manifest_sha256):
        raise MLFailure("OCR_HANDOFF_INVALID", "ocr_handoff")
    if expected_source_manifest_sha256 is not None:
        if not _is_sha256(expected_source_manifest_sha256) or source_manifest_sha256 != expected_source_manifest_sha256:
            raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")

    engine_manifest = index.get("engine_manifest")
    profile_block = index.get("profile")
    samples_map = index.get("samples")
    if (
        not isinstance(engine_manifest, dict)
        or not _is_sha256(engine_manifest.get("engine_sha256"))
        or not isinstance(profile_block, dict)
        or not isinstance(profile_block.get("profile"), dict)
        or type(profile_block.get("artifact_version")) is not int
        or profile_block["artifact_version"] not in (1, 2)
        or not _is_nonblank_str(profile_block.get("ocr_version"))
        or not _is_sha256(profile_block.get("profile_sha256"))
        or not isinstance(samples_map, dict)
        or not samples_map
    ):
        raise MLFailure("OCR_HANDOFF_INVALID", "ocr_handoff")

    engine_sha256 = engine_manifest["engine_sha256"]
    profile_sha256 = profile_block["profile_sha256"]
    recomputed_profile_sha = compute_profile_sha256(
        profile_block["profile"],
        artifact_version=profile_block["artifact_version"],
        ocr_version=profile_block["ocr_version"],
    )
    if recomputed_profile_sha != profile_sha256:
        raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")

    if expected_engine_sha256 is not None:
        if not _is_sha256(expected_engine_sha256) or engine_sha256 != expected_engine_sha256:
            raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")
    if expected_profile_sha256 is not None:
        if not _is_sha256(expected_profile_sha256) or profile_sha256 != expected_profile_sha256:
            raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")

    verified_samples: dict[str, OcrHandoffSample] = {}
    seen_casefold: set[str] = set()
    for key_sid, entry in samples_map.items():
        if not _is_sample_id(key_sid) or not isinstance(entry, dict):
            raise MLFailure("OCR_HANDOFF_INVALID", "ocr_handoff")
        sid = entry.get("sample_id")
        if sid != key_sid:
            raise MLFailure("OCR_HANDOFF_INVALID", "ocr_handoff")
        folded = sid.casefold()
        if folded in seen_casefold:
            raise MLFailure("DUPLICATE_SAMPLE_ID", "ocr_handoff")
        seen_casefold.add(folded)

        doc_type = entry.get("document_type")
        if doc_type not in ("receipt", "invoice") or entry.get("status") != "ok":
            raise MLFailure("OCR_HANDOFF_INVALID", "ocr_handoff")

        paths = entry.get("paths")
        hashes = entry.get("hashes")
        declared_prov = entry.get("provenance")
        canonical_info = entry.get("canonical")
        if (
            not isinstance(paths, dict)
            or set(paths) != {"ocr", "prepared", "provenance"}
            or not isinstance(hashes, dict)
            or not isinstance(declared_prov, dict)
            or set(declared_prov) != _PROVENANCE_KEYS
            or not isinstance(canonical_info, dict)
            or not _is_sha256(canonical_info.get("sha256"))
        ):
            raise MLFailure("OCR_HANDOFF_INVALID", "ocr_handoff")
        if any(not _is_sha256(v) for v in declared_prov.values()):
            raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")

        ocr_path = _contained_file(root, paths["ocr"], stage="ocr_handoff")
        prepared_path = _contained_file(root, paths["prepared"], stage="ocr_handoff")
        prov_path = _contained_file(root, paths["provenance"], stage="ocr_handoff")

        ocr_data, _, actual_ocr_sha = _read_strict_json(ocr_path, stage="ocr_handoff")
        prepared_data, _, actual_prepared_sha = _read_strict_json(prepared_path, stage="ocr_handoff")
        prov_data, _, actual_prov_sha = _read_strict_json(prov_path, stage="ocr_handoff")

        if (
            hashes.get("ocr_sha256") != actual_ocr_sha
            or hashes.get("prepared_sha256") != actual_prepared_sha
            or hashes.get("provenance_sha256") != actual_prov_sha
        ):
            raise MLFailure("OCR_HANDOFF_HASH_MISMATCH", "ocr_handoff")

        if not isinstance(prov_data, dict) or set(prov_data) != _PROVENANCE_KEYS or prov_data != declared_prov:
            raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")
        if (
            prov_data["input_sha256"] != hashes.get("input_sha256")
            or prov_data["canonical_sha256"] != hashes.get("canonical_sha256")
            or prov_data["canonical_sha256"] != canonical_info["sha256"]
            or prov_data["engine_sha256"] != hashes.get("engine_sha256")
            or prov_data["engine_sha256"] != engine_sha256
            or prov_data["profile_sha256"] != hashes.get("profile_sha256")
            or prov_data["profile_sha256"] != profile_sha256
        ):
            raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")

        _check_no_forbidden_ocr_keys(ocr_data, stage="ocr_handoff")
        _check_no_forbidden_ocr_keys(prepared_data, stage="ocr_handoff")
        try:
            prepared_page = PreparedPage.from_dict(prepared_data)
            ocr_page = OcrPage.from_dict(ocr_data)
            ocr_page.validate_against(prepared_page)
            snapshot_page(ocr_data, prepared_data)
        except (ValueError, TypeError, BaselineError):
            raise MLFailure("OCR_INPUT_INVALID", "ocr_handoff") from None

        if (
            ocr_page.artifact_version != profile_block["artifact_version"]
            or ocr_page.ocr_version != profile_block["ocr_version"]
            or entry.get("artifact_version") != ocr_page.artifact_version
            or entry.get("ocr_version") != ocr_page.ocr_version
            or entry.get("preprocess_version") != prepared_page.preprocess_version
        ):
            raise MLFailure("PROVENANCE_MISMATCH", "ocr_handoff")

        verified_samples[sid] = OcrHandoffSample(
            sample_id=sid,
            document_type=doc_type,
            ocr=ocr_data,
            prepared=prepared_data,
            provenance=dict(prov_data),
            ocr_sha256=actual_ocr_sha,
            prepared_sha256=actual_prepared_sha,
            provenance_sha256=actual_prov_sha,
            artifact_version=ocr_page.artifact_version,
            ocr_version=ocr_page.ocr_version,
            preprocess_version=prepared_page.preprocess_version,
            recognition_status=ocr_page.recognition_status,
            review_flags=tuple(ocr_page.review_flags),
        )

    return VerifiedOcrHandoffIndex(
        bundle_version=BUNDLE_VERSION,
        index_sha256=index_sha256,
        source_manifest_version=source_manifest_version,
        source_manifest_sha256=source_manifest_sha256,
        engine_sha256=engine_sha256,
        profile_sha256=profile_sha256,
        profile=dict(profile_block["profile"]),
        artifact_version=profile_block["artifact_version"],
        ocr_version=profile_block["ocr_version"],
        samples=verified_samples,
    )


def _validate_data_record(record: DataTrainingRecord) -> None:
    if not isinstance(record, DataTrainingRecord):
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    if not _is_sample_id(record.sample_id):
        raise MLFailure("SAMPLE_ID_INVALID", "dataset")
    if not _is_nonblank_str(record.base_id) or not _is_nonblank_str(record.family_id) or not _is_nonblank_str(record.source_group):
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    if record.split == "final":
        raise MLFailure("FINAL_SPLIT_FORBIDDEN", "dataset")
    if record.split not in ALLOWED_TRAINING_SPLITS:
        raise MLFailure("SPLIT_INVALID", "dataset")
    if record.document_type not in ("receipt", "invoice"):
        raise MLFailure("DOCUMENT_TYPE_INVALID", "dataset")
    if not _is_sha256(record.input_sha256):
        raise MLFailure("PROVENANCE_MISMATCH", "dataset")
    if record.canonical_sha256 is not None and not _is_sha256(record.canonical_sha256):
        raise MLFailure("PROVENANCE_MISMATCH", "dataset")
    if record.assignment_group is not None and not _is_nonblank_str(record.assignment_group):
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    if record.content_sha256 is not None and not _is_sha256(record.content_sha256):
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    if record.population_id is not None and not _is_nonblank_str(record.population_id):
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    if record.dataset_manifest_sha256 is not None and not _is_sha256(record.dataset_manifest_sha256):
        raise MLFailure("PROVENANCE_MISMATCH", "dataset")


def _check_cross_population_leakage(
    records: Sequence[DataTrainingRecord],
    reference_records: Sequence[DataTrainingRecord] | None,
    *,
    target_split: str,
) -> str | None:
    """Reject final split, mixed splits, mismatched populations, and cross-split group/hash overlap."""
    populations: set[str | None] = set()
    for record in records:
        if record.split == "final":
            raise MLFailure("FINAL_SPLIT_FORBIDDEN", "dataset")
        if record.split != target_split:
            raise MLFailure("CROSS_POPULATION_LEAKAGE", "dataset")
        populations.add(record.population_id)
    if len(populations) > 1:
        raise MLFailure("CROSS_POPULATION_LEAKAGE", "dataset")
    population_id = next(iter(populations)) if populations else None

    if not reference_records:
        return population_id

    train_ids = {r.sample_id.casefold() for r in records}
    train_inputs = {r.input_sha256 for r in records}
    train_contents = {r.content_sha256 for r in records if r.content_sha256 is not None}

    combined_for_disjoint: list[dict[str, str]] = [
        {
            "base_id": r.base_id,
            "family_id": r.family_id,
            "source_group": r.source_group,
            "assignment_group": r.assignment_group or f"{r.source_group}::{r.family_id}",
            "split": r.split,
        }
        for r in records
    ]

    for ref in reference_records:
        if not isinstance(ref, DataTrainingRecord):
            raise MLFailure("DATA_RECORD_INVALID", "dataset")
        if ref.split == "final":
            raise MLFailure("FINAL_SPLIT_FORBIDDEN", "dataset")
        if ref.split not in ALLOWED_TRAINING_SPLITS:
            raise MLFailure("SPLIT_INVALID", "dataset")
        if not _is_sample_id(ref.sample_id) or not _is_sha256(ref.input_sha256):
            raise MLFailure("DATA_RECORD_INVALID", "dataset")
        if ref.split == target_split:
            continue
        if ref.sample_id.casefold() in train_ids:
            raise MLFailure("CROSS_POPULATION_LEAKAGE", "dataset")
        if ref.input_sha256 in train_inputs:
            raise MLFailure("CROSS_POPULATION_LEAKAGE", "dataset")
        if ref.content_sha256 is not None and ref.content_sha256 in train_contents:
            raise MLFailure("CROSS_POPULATION_LEAKAGE", "dataset")
        combined_for_disjoint.append(
            {
                "base_id": ref.base_id,
                "family_id": ref.family_id,
                "source_group": ref.source_group,
                "assignment_group": ref.assignment_group or f"{ref.source_group}::{ref.family_id}",
                "split": ref.split,
            }
        )

    try:
        assert_disjoint(combined_for_disjoint)
    except ValueError:
        raise MLFailure("CROSS_POPULATION_LEAKAGE", "dataset") from None
    return population_id


def _resolve_qwen_config(config: Any) -> QwenConfig:
    if isinstance(config, QwenConfig):
        return config
    to_infer = getattr(config, "to_inference_config", None)
    if callable(to_infer):
        resolved = to_infer()
        if isinstance(resolved, QwenConfig):
            return resolved
    raise MLFailure("CONFIG_INVALID", "config")


def join_training_dataset(
    ocr_handoff: VerifiedOcrHandoffIndex | Path | str,
    data_records: Sequence[DataTrainingRecord],
    config: QwenConfig | Any,
    *,
    expected_engine_sha256: str,
    expected_profile_sha256: str,
    target_split: Literal["train", "dev"] = "train",
    expected_dataset_manifest_sha256: str | None = None,
    expected_canonical_sha256s: Mapping[str, str] | None = None,
    reference_records: Sequence[DataTrainingRecord] | None = None,
) -> TrainingDataset:
    """Join verified AI-2 OCR handoff records with Data records by `sample_id`.

    Fails closed when:
    - engine/profile provenance pins are missing or mismatched,
    - `target_split` or any record is `final`,
    - records mix splits or populations or leak across splits (`base_id`/`family_id`/`source_group`/hashes),
    - `sample_id`s are missing, duplicated (exact or casefold alias), or mismatched between OCR and Data,
    - `document_type`, `input_sha256`, or `canonical_sha256` disagrees,
    - `gold` fails strict selected business schema or `labels` violate four-state invariants,
    - OCR payload contains gold transcript or fails `OcrPage`/`PreparedPage` validation.
    """
    config = _resolve_qwen_config(config)
    if target_split == "final":
        raise MLFailure("FINAL_SPLIT_FORBIDDEN", "dataset")
    if target_split not in ALLOWED_TRAINING_SPLITS:
        raise MLFailure("SPLIT_INVALID", "dataset")
    if not _is_sha256(expected_engine_sha256) or not _is_sha256(expected_profile_sha256):
        raise MLFailure("ARTIFACT_PINS_MISSING", "dataset")
    if expected_dataset_manifest_sha256 is not None and not _is_sha256(expected_dataset_manifest_sha256):
        raise MLFailure("ARTIFACT_PINS_MISSING", "dataset")

    if isinstance(ocr_handoff, VerifiedOcrHandoffIndex):
        handoff_index = ocr_handoff
    else:
        handoff_index = load_ocr_handoff_bundle(
            ocr_handoff,
            expected_engine_sha256=expected_engine_sha256,
            expected_profile_sha256=expected_profile_sha256,
            expected_source_manifest_sha256=expected_dataset_manifest_sha256,
        )

    if handoff_index.bundle_version != BUNDLE_VERSION:
        raise MLFailure("OCR_HANDOFF_INVALID", "dataset")
    if (
        handoff_index.engine_sha256 != expected_engine_sha256
        or handoff_index.profile_sha256 != expected_profile_sha256
    ):
        raise MLFailure("PROVENANCE_MISMATCH", "dataset")
    if (
        expected_dataset_manifest_sha256 is not None
        and handoff_index.source_manifest_sha256 != expected_dataset_manifest_sha256
    ):
        raise MLFailure("PROVENANCE_MISMATCH", "dataset")

    if not isinstance(data_records, Sequence) or isinstance(data_records, (str, bytes)) or not data_records:
        raise MLFailure("DATA_RECORDS_EMPTY", "dataset")

    by_id: dict[str, DataTrainingRecord] = {}
    seen_casefold: set[str] = set()
    ordered_ids: list[str] = []
    for record in data_records:
        _validate_data_record(record)
        folded = record.sample_id.casefold()
        if record.sample_id in by_id or folded in seen_casefold:
            raise MLFailure("DUPLICATE_SAMPLE_ID", "dataset")
        if (
            record.dataset_manifest_sha256 is not None
            and record.dataset_manifest_sha256 != handoff_index.source_manifest_sha256
        ):
            raise MLFailure("CROSS_POPULATION_LEAKAGE", "dataset")
        by_id[record.sample_id] = record
        seen_casefold.add(folded)
        ordered_ids.append(record.sample_id)

    population_id = _check_cross_population_leakage(data_records, reference_records, target_split=target_split)

    ocr_ids = set(handoff_index.samples)
    data_ids = set(by_id)
    if ocr_ids != data_ids:
        raise MLFailure("SAMPLE_ID_JOIN_MISMATCH", "dataset")

    if expected_canonical_sha256s is not None:
        if set(expected_canonical_sha256s) != data_ids or any(
            not _is_sha256(val) for val in expected_canonical_sha256s.values()
        ):
            raise MLFailure("PROVENANCE_MISMATCH", "dataset")

    validators = {
        doc_type: Draft202012Validator(business_schema(config, doc_type))
        for doc_type in ("receipt", "invoice")
    }

    examples: list[JoinedTrainingRecord] = []
    excluded: list[ExcludedTrainingRecord] = []
    status_totals: dict[str, int] = {state: 0 for state in FOUR_STATES}
    membership_entries: list[dict[str, Any]] = []

    for sid in ordered_ids:
        data_rec = by_id[sid]
        ocr_rec = handoff_index.samples[sid]
        if ocr_rec.sample_id != sid:
            raise MLFailure("SAMPLE_ID_JOIN_MISMATCH", "dataset")
        if ocr_rec.document_type != data_rec.document_type:
            raise MLFailure("DOCUMENT_TYPE_MISMATCH", "dataset")

        prov = ocr_rec.provenance
        if set(prov) != _PROVENANCE_KEYS or any(not _is_sha256(v) for v in prov.values()):
            raise MLFailure("PROVENANCE_MISMATCH", "dataset")
        if prov["input_sha256"] != data_rec.input_sha256:
            raise MLFailure("PROVENANCE_MISMATCH", "dataset")
        if prov["engine_sha256"] != expected_engine_sha256 or prov["profile_sha256"] != expected_profile_sha256:
            raise MLFailure("PROVENANCE_MISMATCH", "dataset")
        if data_rec.canonical_sha256 is not None and prov["canonical_sha256"] != data_rec.canonical_sha256:
            raise MLFailure("PROVENANCE_MISMATCH", "dataset")
        if expected_canonical_sha256s is not None and prov["canonical_sha256"] != expected_canonical_sha256s[sid]:
            raise MLFailure("PROVENANCE_MISMATCH", "dataset")

        _check_no_forbidden_ocr_keys(ocr_rec.ocr, stage="dataset")
        _check_no_forbidden_ocr_keys(ocr_rec.prepared, stage="dataset")
        try:
            prepared_page = PreparedPage.from_dict(ocr_rec.prepared)
            ocr_page = OcrPage.from_dict(ocr_rec.ocr)
            ocr_page.validate_against(prepared_page)
            snapshot_page(ocr_rec.ocr, ocr_rec.prepared)
        except (ValueError, TypeError, BaselineError):
            raise MLFailure("OCR_INPUT_INVALID", "dataset") from None

        if not isinstance(data_rec.gold, dict):
            raise MLFailure("GOLD_SCHEMA_INVALID", "dataset")
        _canonical_json_bytes(data_rec.gold, stage="dataset")
        if not validators[data_rec.document_type].is_valid(data_rec.gold):
            raise MLFailure("GOLD_SCHEMA_INVALID", "dataset")

        validated_labels = _validate_field_labels_obj(data_rec.gold, data_rec.labels)
        counts = {state: 0 for state in FOUR_STATES}
        obscured_ptrs: list[str] = []
        unlabeled_ptrs: list[str] = []
        for field_label in validated_labels.fields:
            counts[field_label.status] += 1
            status_totals[field_label.status] += 1
            if field_label.status == "obscured":
                obscured_ptrs.append(field_label.pointer)
            elif field_label.status == "unlabeled":
                unlabeled_ptrs.append(field_label.pointer)

        target_json = serialize_business_target(data_rec.gold, data_rec.document_type)
        gold_sha256 = hashlib.sha256(target_json.encode("utf-8")).hexdigest()
        labels_payload = [
            {"pointer": item.pointer, "value": item.value, "status": item.status}
            for item in validated_labels.fields
        ]
        labels_sha256 = hashlib.sha256(_canonical_json_bytes(labels_payload, stage="dataset")).hexdigest()

        eligible = not obscured_ptrs and not unlabeled_ptrs
        membership_entries.append(
            {
                "sample_id": sid,
                "base_id": data_rec.base_id,
                "family_id": data_rec.family_id,
                "source_group": data_rec.source_group,
                "split": data_rec.split,
                "document_type": data_rec.document_type,
                "input_sha256": prov["input_sha256"],
                "canonical_sha256": prov["canonical_sha256"],
                "ocr_sha256": ocr_rec.ocr_sha256,
                "prepared_sha256": ocr_rec.prepared_sha256,
                "gold_sha256": gold_sha256,
                "labels_sha256": labels_sha256,
                "full_json_eligible": eligible,
            }
        )

        if not eligible:
            if obscured_ptrs and unlabeled_ptrs:
                reason = "OBSCURED_AND_UNLABELED_FIELDS_EXCLUDED"
            elif obscured_ptrs:
                reason = "OBSCURED_FIELDS_EXCLUDED"
            else:
                reason = "UNLABELED_FIELDS_EXCLUDED"
            excluded.append(
                ExcludedTrainingRecord(
                    sample_id=sid,
                    base_id=data_rec.base_id,
                    family_id=data_rec.family_id,
                    source_group=data_rec.source_group,
                    split=target_split,
                    document_type=data_rec.document_type,
                    reason=reason,
                    status_counts=counts,
                    obscured_pointers=tuple(obscured_ptrs),
                    unlabeled_pointers=tuple(unlabeled_ptrs),
                )
            )
            continue

        examples.append(
            JoinedTrainingRecord(
                sample_id=sid,
                base_id=data_rec.base_id,
                family_id=data_rec.family_id,
                source_group=data_rec.source_group,
                assignment_group=data_rec.assignment_group,
                split=target_split,
                document_type=data_rec.document_type,
                ocr=ocr_rec.ocr,
                prepared=ocr_rec.prepared,
                provenance=dict(prov),
                gold=dict(data_rec.gold),
                target_json=target_json,
                field_labels=validated_labels,
                status_counts=counts,
                full_json_eligible=True,
                gold_sha256=gold_sha256,
                labels_sha256=labels_sha256,
            )
        )

    sample_membership_sha256 = hashlib.sha256(
        _canonical_json_bytes(
            {
                "adapter_version": DATASET_ADAPTER_VERSION,
                "split": target_split,
                "source_manifest_sha256": handoff_index.source_manifest_sha256,
                "engine_sha256": expected_engine_sha256,
                "profile_sha256": expected_profile_sha256,
                "members": membership_entries,
            },
            stage="dataset",
        )
    ).hexdigest()

    serialization_sha256 = hashlib.sha256(
        _canonical_json_bytes(
            {
                "adapter_version": DATASET_ADAPTER_VERSION,
                "serialization_version": config.serialization_version,
                "target_serialization_version": TARGET_SERIALIZATION_VERSION,
                "prompt_version": prompt_version(config.serialization_version),
                "label_adapter_version": LABEL_ADAPTER_VERSION,
                "schema_sha256": config.schema_sha256,
                "max_input_tokens": config.max_input_tokens,
                "max_ocr_tokens": config.max_ocr_tokens,
                "max_new_tokens": config.max_new_tokens,
                "max_sequence_tokens": config.max_sequence_tokens,
                "label_ignore_index": LABEL_IGNORE_INDEX,
                "truncation": False,
                "packing": False,
            },
            stage="dataset",
        )
    ).hexdigest()

    return TrainingDataset(
        adapter_version=DATASET_ADAPTER_VERSION,
        split=target_split,
        population_id=population_id,
        source_manifest_sha256=handoff_index.source_manifest_sha256,
        ocr_bundle_version=handoff_index.bundle_version,
        ocr_index_sha256=handoff_index.index_sha256,
        engine_sha256=expected_engine_sha256,
        profile_sha256=expected_profile_sha256,
        schema_sha256=config.schema_sha256,
        serialization_version=config.serialization_version,
        target_serialization_version=TARGET_SERIALIZATION_VERSION,
        prompt_version=prompt_version(config.serialization_version),
        label_adapter_version=LABEL_ADAPTER_VERSION,
        sample_membership_sha256=sample_membership_sha256,
        serialization_sha256=serialization_sha256,
        examples=tuple(examples),
        excluded=tuple(excluded),
        status_totals=status_totals,
        counts={
            "joined": len(ordered_ids),
            "eligible": len(examples),
            "excluded": len(excluded),
            "receipt": sum(1 for item in examples if item.document_type == "receipt"),
            "invoice": sum(1 for item in examples if item.document_type == "invoice"),
        },
    )


class TrainingCollator:
    """Build assistant-only supervised batches with prompt/OCR/pad masked to -100."""

    def __init__(
        self,
        config: QwenConfig | Any,
        tokenizer: Any,
        *,
        label_ignore_index: int = LABEL_IGNORE_INDEX,
    ) -> None:
        config = _resolve_qwen_config(config)
        if type(label_ignore_index) is not int or label_ignore_index != LABEL_IGNORE_INDEX:
            raise MLFailure("CONFIG_INVALID", "collate")
        eos_id = getattr(tokenizer, "eos_token_id", None)
        pad_id = getattr(tokenizer, "pad_token_id", None)
        if type(eos_id) is not int or eos_id < 0 or type(pad_id) is not int or pad_id < 0:
            raise MLFailure("TOKENIZER_INCOMPATIBLE", "collate")
        self.config = config
        self.tokenizer = tokenizer
        self.eos_token_id = eos_id
        self.pad_token_id = pad_id
        self.label_ignore_index = label_ignore_index

    def encode_example(self, record: JoinedTrainingRecord) -> tuple[OcrPrompt, tuple[int, ...], tuple[int, ...]]:
        if not isinstance(record, JoinedTrainingRecord):
            raise MLFailure("DATA_RECORD_INVALID", "collate")
        if (
            not record.full_json_eligible
            or record.status_counts.get("obscured", 0) != 0
            or record.status_counts.get("unlabeled", 0) != 0
            or any(fl.status in ("obscured", "unlabeled") for fl in record.field_labels.fields)
        ):
            raise MLFailure("UNSUPERVISABLE_LABEL_STATUS", "collate")

        _check_no_forbidden_ocr_keys(record.ocr, stage="collate")
        prompt = build_prompt(
            record.ocr,
            record.prepared,
            record.provenance,
            record.document_type,
            self.config,
            self.tokenizer,
        )
        try:
            target_tokens = self.tokenizer.encode(record.target_json, add_special_tokens=False)
        except Exception:
            raise MLFailure("TOKENIZER_FAILED", "collate") from None
        if (
            not isinstance(target_tokens, list)
            or not target_tokens
            or any(type(token) is not int or token < 0 for token in target_tokens)
        ):
            raise MLFailure("TOKENIZER_FAILED", "collate")

        assistant_ids = tuple(target_tokens) + (self.eos_token_id,)
        if (
            len(assistant_ids) > self.config.max_new_tokens
            or len(prompt.input_ids) + len(assistant_ids) > self.config.max_sequence_tokens
        ):
            raise MLFailure("CONTEXT_OVERFLOW", "collate")

        full_ids = prompt.input_ids + assistant_ids
        labels = (self.label_ignore_index,) * len(prompt.input_ids) + assistant_ids
        return prompt, full_ids, labels

    def collate(self, examples: Sequence[JoinedTrainingRecord]) -> CollatedBatch:
        if not examples:
            raise MLFailure("EMPTY_BATCH", "collate")
        encoded: list[tuple[JoinedTrainingRecord, OcrPrompt, tuple[int, ...], tuple[int, ...]]] = []
        for record in examples:
            prompt, full_ids, labels = self.encode_example(record)
            encoded.append((record, prompt, full_ids, labels))

        max_len = max(len(item[2]) for item in encoded)
        batch_input_ids: list[tuple[int, ...]] = []
        batch_attention_mask: list[tuple[int, ...]] = []
        batch_labels: list[tuple[int, ...]] = []
        prompt_lengths: list[int] = []
        target_lengths: list[int] = []
        prompt_sha256s: list[str] = []

        for record, prompt, full_ids, labels in encoded:
            pad_len = max_len - len(full_ids)
            batch_input_ids.append(full_ids + (self.pad_token_id,) * pad_len)
            batch_attention_mask.append((1,) * len(full_ids) + (0,) * pad_len)
            batch_labels.append(labels + (self.label_ignore_index,) * pad_len)
            prompt_lengths.append(len(prompt.input_ids))
            target_lengths.append(len(full_ids) - len(prompt.input_ids))
            prompt_sha256s.append(
                hashlib.sha256(_canonical_json_bytes(list(prompt.messages), stage="collate")).hexdigest()
            )

        serialization_sha256 = hashlib.sha256(
            _canonical_json_bytes(
                {
                    "serialization_version": self.config.serialization_version,
                    "target_serialization_version": TARGET_SERIALIZATION_VERSION,
                    "prompt_version": prompt_version(self.config.serialization_version),
                    "schema_sha256": self.config.schema_sha256,
                    "pad_token_id": self.pad_token_id,
                    "eos_token_id": self.eos_token_id,
                    "label_ignore_index": self.label_ignore_index,
                },
                stage="collate",
            )
        ).hexdigest()

        return CollatedBatch(
            sample_ids=tuple(item[0].sample_id for item in encoded),
            document_types=tuple(item[0].document_type for item in encoded),
            input_ids=tuple(batch_input_ids),
            attention_mask=tuple(batch_attention_mask),
            labels=tuple(batch_labels),
            prompt_lengths=tuple(prompt_lengths),
            target_lengths=tuple(target_lengths),
            pad_token_id=self.pad_token_id,
            eos_token_id=self.eos_token_id,
            label_ignore_index=self.label_ignore_index,
            prompt_sha256s=tuple(prompt_sha256s),
            serialization_sha256=serialization_sha256,
        )


def token_preflight(dataset: TrainingDataset, collator: TrainingCollator) -> dict[str, Any]:
    """Measure every eligible example without model weights; never truncate/drop.

    Return all failures so the controller sees the entire population, rather
    than only the first overflow. Payloads/gold/text never enter this report.
    """
    rows = []
    for record in dataset.examples:
        row = {"sample_id": record.sample_id, "document_type": record.document_type}
        try:
            prompt, ids, labels = collator.encode_example(record)
            n = len(prompt.input_ids)
            if (labels[:n] != (LABEL_IGNORE_INDEX,) * n or labels[n:] != ids[n:]
                    or labels[-1] != collator.eos_token_id):
                raise MLFailure("ASSISTANT_MASK_INVALID", "collate")
            row.update(prompt_tokens=n, ocr_tokens=prompt.ocr_tokens,
                       target_tokens=len(ids) - n, sequence_tokens=len(ids),
                       prompt_sha256=hashlib.sha256(
                           _canonical_json_bytes(prompt.messages, stage="collate")).hexdigest())
        except MLFailure as err:
            row.update(error_code=err.code, stage=err.stage)
        rows.append(row)
    return {"ok": bool(rows) and all("error_code" not in row for row in rows),
            "counts": dict(dataset.counts), "rows": rows,
            "serialization_version": dataset.serialization_version,
            "prompt_version": dataset.prompt_version,
            "serialization_sha256": dataset.serialization_sha256,
            "sample_membership_sha256": dataset.sample_membership_sha256,
            "excluded": [{"sample_id": r.sample_id, "reason": r.reason} for r in dataset.excluded]}
