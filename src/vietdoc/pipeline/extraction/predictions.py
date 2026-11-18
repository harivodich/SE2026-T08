"""Offline prediction producer for Data's vietdoc.predictions.v1 proposal.

No gold/labels/evaluator imports. Renderer mode is explicit simulated OCR input;
it drops annotation pointers and is never described as native inference.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct

from vietdoc.contracts.compute import BUSINESS_SCHEMA, default_contracts_dir
from vietdoc.pipeline.normalization import POLICY_VERSION
from .baseline import BASELINE_VERSION, extract_baseline
from .ocr_input import BaselineError, snapshot_page

ARTIFACT_VERSION = "vietdoc.predictions.v1"
FIXTURE_OCR_VERSION = "renderer-simulated-ocr.v1"
FIXTURE_PREPROCESS_VERSION = "renderer-identity.fixture.v1"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")  # Data sample_id grammar
HASH = re.compile(r"^[0-9a-f]{64}$")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BaselineError("JSON_INVALID")
        result[key] = value
    return result


def _json(data: bytes):
    def constant(_):
        raise BaselineError("JSON_INVALID")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_unique, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BaselineError("JSON_INVALID") from error


def _read(path: Path, cap=4 * 1024 * 1024) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise BaselineError("PROFILE_EXCEEDED")
    return data


def _path(root: Path, raw: str) -> Path:
    if (not isinstance(raw, str) or PurePosixPath(raw).is_absolute() or ":" in raw or "\\" in raw
            or any(part in ("", ".", "..") for part in raw.split("/"))):
        raise BaselineError("ASSET_PATH_INVALID")
    target = root / raw
    if not target.resolve().is_relative_to(root):
        raise BaselineError("ASSET_PATH_INVALID")
    current = root
    for part in raw.split("/"):
        current = current / part
        attributes = getattr(current.lstat(), "st_file_attributes", 0)
        if current.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise BaselineError("ASSET_PATH_INVALID")
    return target


def _asset(root: Path, entry: dict, cap=4 * 1024 * 1024) -> bytes:
    if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str) or not HASH.fullmatch(entry["sha256"]):
        raise BaselineError("ASSET_HASH_INVALID")
    data = _read(_path(root, entry.get("path")), cap)
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise BaselineError("ASSET_HASH_MISMATCH")
    return data


def _manifest_path(root: Path, path: Path) -> Path:
    path = path if path.is_absolute() else root / path
    try:
        return _path(root, path.absolute().relative_to(root).as_posix())
    except ValueError as error:
        raise BaselineError("ASSET_PATH_INVALID") from error


def _index(samples):
    if not isinstance(samples, list) or not samples:
        raise BaselineError("MANIFEST_INVALID")
    records = {}
    for sample in samples:
        sid = sample.get("sample_id") if isinstance(sample, dict) else None
        if not isinstance(sid, str) or not ID.fullmatch(sid) or sid in records:
            raise BaselineError("MANIFEST_INVALID")
        records[sid] = sample
    return records


def renderer_input(root: Path, sample: dict):
    """Fixture adapter only: renderer text/boxes -> simulated AI1-shaped input."""
    assets = sample.get("assets", {})
    if not isinstance(assets, dict) or "regions.json" not in assets or "png" not in assets:
        raise BaselineError("FIXTURE_INPUT_MISSING")
    regions = _json(_asset(root, assets["regions.json"]))
    if not isinstance(regions, dict) or not isinstance(regions.get("regions"), list):
        raise BaselineError("FIXTURE_INPUT_INVALID")
    if (regions.get("convention") != "renderer-local-v1; not approved shared geometry"
            or regions.get("origin") != "top-left" or regions.get("units") != "pixels"
            or regions.get("transform") != "identity; PNG is the rendered page" or regions.get("page") != 0):
        raise BaselineError("FIXTURE_CONVENTION_UNSUPPORTED")
    png = _asset(root, assets["png"], 20 * 1024 * 1024)
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise BaselineError("FIXTURE_INPUT_INVALID")
    width, height = struct.unpack(">II", png[16:24])
    if not width or not height or (width, height) != (regions.get("width"), regions.get("height")):
        raise BaselineError("FIXTURE_INPUT_INVALID")
    blocks = []
    for index, item in enumerate(regions.get("regions", [])):
        if not isinstance(item, dict):
            raise BaselineError("FIXTURE_INPUT_INVALID")
        box = item.get("bbox_px")
        if not isinstance(box, list) or len(box) != 4 or any(type(n) not in (int, float) for n in box):
            raise BaselineError("FIXTURE_INPUT_INVALID")
        x0, y0, x1, y1 = box
        # Annotation pointer, label status and gold are intentionally never used.
        blocks.append(dict(block_id=f"fixture-{index}", text=item.get("text"),
                           quad=[[x0 / width, y0 / height], [x1 / width, y0 / height],
                                 [x1 / width, y1 / height], [x0 / width, y1 / height]],
                           score=None, geometry_reason=None))
    page = dict(page=0, width=width, height=height, ocr_version=FIXTURE_OCR_VERSION, blocks=blocks)
    image = dict(width=width, height=height, color_order="RGB", dtype="uint8")
    prepared = dict(page=0, canonical=image, processed=dict(image), preprocess_version=FIXTURE_PREPROCESS_VERSION,
                    geometry_status="available", inverse_transform=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], geometry_reason=None)
    canonical = dict(page=0, width=width, height=height, sha256=assets["png"]["sha256"])
    return page, prepared, canonical


def export_predictions(root: Path, manifest_path: Path, output_dir: Path, *,
                       ocr_inputs: Path | None = None, renderer_fixtures: bool = False) -> dict:
    root = root.resolve()
    if (ocr_inputs is None) == (not renderer_fixtures):
        raise BaselineError("INPUT_MODE_REQUIRED")
    manifest_bytes = _read(_manifest_path(root, manifest_path))
    manifest = _json(manifest_bytes)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str) or not manifest["version"]:
        raise BaselineError("MANIFEST_INVALID")
    samples = _index(manifest.get("samples"))
    for sample in samples.values():
        if sample.get("document_type") not in ("receipt", "invoice") or sample.get("schema_id") != BUSINESS_SCHEMA:
            raise BaselineError("MANIFEST_INVALID")
    inputs, input_hash = {}, None
    ocr_version, preprocess_version = FIXTURE_OCR_VERSION, FIXTURE_PREPROCESS_VERSION
    if ocr_inputs is not None:
        input_bytes = _read(_manifest_path(root, ocr_inputs))
        supplied = _json(input_bytes)
        if not isinstance(supplied, dict) or supplied.get("artifact_version") != "vietdoc.baseline-inputs.v1":
            raise BaselineError("OCR_INPUT_INVALID")
        inputs = _index(supplied.get("samples"))
        if set(inputs) - samples.keys():
            raise BaselineError("MANIFEST_INVALID")
        ocr_version, preprocess_version = supplied.get("ocr_version"), supplied.get("preprocess_version")
        if any(not isinstance(version, str) or not version.strip() for version in (ocr_version, preprocess_version)):
            raise BaselineError("OCR_INPUT_INVALID")
        input_hash = hashlib.sha256(input_bytes).hexdigest()
    records, snapshots = [], {}
    for sid, sample in samples.items():
        kind = sample["document_type"]
        try:
            canonical = None
            if renderer_fixtures:
                page, prepared, canonical = renderer_input(root, sample)
            else:
                if sid not in inputs:
                    raise BaselineError("OCR_INPUT_MISSING")
                source = inputs[sid]
                if not {"ocr", "prepared"} <= source.keys():
                    raise BaselineError("OCR_INPUT_MISSING")
                page = _json(_asset(root, source["ocr"]))
                prepared = _json(_asset(root, source["prepared"]))
            snapshot = snapshot_page(page, prepared)
            if (snapshot.ocr_version, snapshot.preprocess_version) != (ocr_version, preprocess_version):
                raise BaselineError("PROVENANCE_MISMATCH")
            snapshots[sid] = dict(page=0, **asdict(snapshot))
            result = extract_baseline(page, kind, prepared=prepared)
            record = dict(sample_id=sid, status="ok", document_type=kind, schema_version=f"{kind}.v1",
                          **asdict(result), ocr_text="\n".join(block.text for block in snapshot.blocks))
            if canonical is not None:
                record.update(canonical_page=canonical, geometry_convention="canonical-normalized-quad-v1")
            records.append(record)
        except BaselineError as error:
            records.append(dict(sample_id=sid, status="failed", error=error.code))
        except OSError:
            records.append(dict(sample_id=sid, status="failed", error="INPUT_STORAGE_UNAVAILABLE"))
    directory = Path(__file__).parent
    source_hashes = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                     for name in ("ocr_input.py", "table.py", "baseline.py", "predictions.py")}
    artifact = dict(artifact_version=ARTIFACT_VERSION, dataset_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                    dataset_version=manifest["version"], model_version=BASELINE_VERSION, normalizer_version=POLICY_VERSION,
                    ocr_version=ocr_version, preprocess_version=preprocess_version, schema_version=BUSINESS_SCHEMA,
                    schema_sha256=hashlib.sha256((default_contracts_dir() / "business.schema.json").read_bytes()).hexdigest(),
                    target_evaluator_versions=["d3.1.v1", "d3.2.v1"], evaluator_policy_status="proposed; consumer review pending",
                    input_mode="renderer-fixture" if renderer_fixtures else "ocr-artifact",
                    actual_ocr=False if renderer_fixtures else None, ocr_inputs_sha256=input_hash,
                    source_sha256=source_hashes, predictions=records)
    prediction_bytes = (json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    diagnostics = dict(artifact_version="vietdoc.ocr-diagnostics.v1",
                       predictions_sha256=hashlib.sha256(prediction_bytes).hexdigest(),
                       dataset_manifest_sha256=artifact["dataset_manifest_sha256"],
                       ocr_inputs_sha256=input_hash,
                       samples=[dict(sample_id=record["sample_id"], status=record["status"],
                                     ocr=snapshots.get(record["sample_id"]),
                                     **({"error": record["error"]} if record["status"] == "failed" else {}))
                                for record in records])
    diagnostic_bytes = (json.dumps(diagnostics, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    # Keep predictions.v1 unchanged; companion diagnostics bind these exact bytes.
    # New output directories only; never overwrite a user's prediction artifact.
    output_dir.mkdir(parents=True, exist_ok=False)
    temporary = output_dir / "predictions.json.tmp"
    temporary.write_bytes(prediction_bytes)
    temporary.rename(output_dir / "predictions.json")
    temporary = output_dir / "ocr-diagnostics.json.tmp"
    temporary.write_bytes(diagnostic_bytes)
    temporary.rename(output_dir / "ocr-diagnostics.json")
    return artifact
