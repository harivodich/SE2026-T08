"""Offline audit of pinned native handoffs/cache indices; never runs inference.

Run after the Data archive receiver. Native report and every consumer index need
out-of-band SHA256 pins. This local diagnostic neither approves splits nor
certifies model quality; renderer reading-order/evaluation policy is Proposed.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import unicodedata

from PIL import Image

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.data.manifest import asset_path, require, sha
from vietdoc.evaluation.policy import POLICY, text
from vietdoc.evaluation.scalar_ocr import dataset_version, evaluate, load_bundle, metric
from vietdoc.ml.ocr_handoff import BUNDLE_VERSION, compute_profile_sha256
from vietdoc.pipeline.geometry import canonical_quad, processed_quad
from vietdoc.pipeline.ocr.diagnose import _read, _write
from vietdoc.pipeline.ocr.handoff import HANDOFF_REPORT_VERSION

VERSION = "vietdoc.ocr-audit.v1"
GROUPS = ("document_type", "base_id", "family_id", "variant", "row_count", "split")


def _pinned(path, expected):
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "INVALID_PIN")
    with Path(path).open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    require(len(raw) <= 8 * 1024 * 1024, "JSON_BYTE_CAP")
    require(sha256(raw).hexdigest() == expected, "PIN_MISMATCH")
    value = _read(raw)
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def _ids(records):
    require(isinstance(records, list) and 0 < len(records) <= 200, "INVALID_POPULATION")
    require(all(isinstance(r, dict) for r in records), "INVALID_POPULATION")
    ids = [r["sample_id"] for r in records]
    require(all(isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", s)
                for s in ids), "INVALID_SAMPLE_ID")
    require(len({s.casefold() for s in ids}) == len(ids), "DUPLICATE_SAMPLE_ID")
    return dict(zip(ids, records))


def _image(path, size, declaration=None):
    # Apply caps before decoding; image files remain data, not executable input.
    require(0 < path.stat().st_size <= 20 * 1024 * 1024, "IMAGE_BYTE_CAP")
    raw = path.read_bytes()
    with Image.open(BytesIO(raw), formats=("PNG",)) as image:
        require(image.size == size and image.mode == "RGB" and image.n_frames == 1
                and size[0] * size[1] <= 20_000_000, "IMAGE_FRAME_MISMATCH")
        image.load()
        pixels = sha256(image.tobytes()).hexdigest()
    if declaration is not None:
        require((declaration["width"], declaration["height"]) == size
                and declaration["sha256"] == sha256(raw).hexdigest()
                and declaration["size_bytes"] == len(raw)
                and declaration["rgb_pixel_sha256"] == pixels, "CANONICAL_PIN_MISMATCH")
    return dict(width=size[0], height=size[1], size_bytes=len(raw),
                sha256=sha256(raw).hexdigest(), rgb_pixel_sha256=pixels)


def _cache_accounting(index, native, counts):
    """Each split export accounts for the whole report, including unselected IDs."""
    samples, excluded = index["samples"], index["excluded"]
    require(isinstance(samples, dict) and isinstance(excluded, list), "CACHE_ACCOUNTING_MISMATCH")
    expected_counts = dict(requested=counts["requested"], exported=len(samples), excluded=len(excluded),
                           **{key: counts[key] for key in ("ok", "failed", "not_run")})
    declared = index["counts"]
    require(isinstance(declared, dict) and all(type(v) is int for v in declared.values())
            and declared == expected_counts, "CACHE_ACCOUNTING_MISMATCH")
    require(len(excluded) <= len(native) and all(isinstance(e, dict) for e in excluded),
            "CACHE_EXCLUSIONS_MISMATCH")
    omitted = {e["sample_id"]: e for e in excluded}
    require(len(omitted) == len(excluded) and set(omitted) == set(native) - set(samples),
            "CACHE_EXCLUSIONS_MISMATCH")
    for sid, entry in omitted.items():
        run = native[sid]
        expected = dict(sample_id=sid, document_type=run["document_type"], status=run["status"],
                        stage=run.get("stage", "export"),
                        reason="NOT_SELECTED" if run["status"] == "ok" else run["error_code"],
                        error_code=None if run["status"] == "ok" else run["error_code"])
        require(entry == expected, "CACHE_EXCLUSIONS_MISMATCH")


def _rates(counts):
    c = Counter(counts)
    excluded = {"no_full_page_gold": c["excluded_no_full_page_gold"]}
    return dict(counts=dict(counts), cer=metric(c["character_edits"], c["reference_characters"],
        c["eligible_samples"], excluded), wer=metric(c["word_edits"], c["reference_words"],
        c["eligible_samples"], excluded))


def _strip_marks(value):
    return "".join(c for c in unicodedata.normalize("NFD", value)
                   if unicodedata.category(c) != "Mn")


def audit(data_root, manifest, manifest_sha256, handoff_root, report_sha256,
          indices, output_dir):
    """Validate all IDs/pins before publishing report.json to a fresh directory.

    ``indices`` is a list of (path, expected_sha256) pairs from AI2 bridge
    exports. Split identity comes from Data, not index filenames. Failed/not_run
    samples remain in population even though bridge indices exclude them.
    """
    data_root, manifest, handoff_root, output = map(Path, (data_root, manifest, handoff_root, output_dir))
    require(not output.exists(), "OUTPUT_EXISTS")
    source = _pinned(manifest, manifest_sha256)
    require(manifest.resolve().is_relative_to(data_root.resolve()), "MANIFEST_OUTSIDE_ROOT")
    by_id = _ids(source["samples"])
    require(all(s.get("split") in ("train", "dev") for s in by_id.values()), "NON_PILOT_SPLIT")
    report = _pinned(handoff_root / "report.json", report_sha256)
    require(report.get("report_version") == HANDOFF_REPORT_VERSION and
            report.get("manifest_sha256") == manifest_sha256 and
            report.get("manifest_version") == source["version"], "REPORT_BINDING_MISMATCH")
    native = _ids(report["samples"])
    require(native.keys() == by_id.keys(), "POPULATION_MISMATCH")
    require(all(s.get("status") in ("ok", "failed", "not_run") and
                type(s.get("native_attempted")) is bool and
                type(s.get("engine_calls")) is int and s["engine_calls"] >= 0
                for s in native.values()), "INVALID_EXECUTION_STATUS")
    counts = dict(requested=len(native), native_attempted=sum(s["native_attempted"] for s in native.values()),
                  **{k: sum(s["status"] == k for s in native.values()) for k in ("ok", "failed", "not_run")})
    require(report["counts"] == counts and report["observed_engine_calls"] ==
            sum(s["engine_calls"] for s in native.values()), "ACCOUNTING_MISMATCH")
    # Reuse the real Data semantic/asset validator; no renderer rerun or gold edits.
    _, gold, _, validation = load_bundle(data_root, manifest)
    gold_by_id = {s["sample_id"]: s for s in gold}
    cache, cache_pins, profiles, engines = {}, {}, [], []
    snapshots = [(manifest, manifest_sha256), (handoff_root / "report.json", report_sha256)]
    require(bool(indices), "CACHE_INDEX_REQUIRED")
    for path, pin in indices:
        path = Path(path)
        index = _pinned(path, pin)
        snapshots.append((path, pin))
        require(index["bundle_version"] == BUNDLE_VERSION and
                index["source_report_sha256"] == report_sha256 and
                index["source_manifest_sha256"] == manifest_sha256, "CACHE_BINDING_MISMATCH")
        cache_pins[path.parent.name + "/" + path.name + ":" + str(len(cache_pins))] = pin
        profiles.append(index["profile"])
        engines.append(index["engine_manifest"])
        _cache_accounting(index, native, counts)
        for sid, entry in index["samples"].items():
            require(isinstance(entry, dict), "CACHE_ID_MISMATCH")
            require(sid in by_id and sid not in cache and entry["sample_id"] == sid and
                    entry["document_type"] == by_id[sid]["document_type"] and entry["status"] == "ok",
                    "CACHE_ID_MISMATCH")
            cache[sid] = (path.parent, entry)
    require(all(p == profiles[0] for p in profiles) and
            all(e == engines[0] for e in engines), "CACHE_PROFILE_MISMATCH")
    require(set(cache) == {sid for sid, s in native.items() if s["status"] == "ok"}, "CACHE_COVERAGE_MISMATCH")

    rows, slices = [], {k: defaultdict(list) for k in GROUPS}
    for sid, sample in by_id.items():
        run = native[sid]
        require(run["document_type"] == sample["document_type"] and
                run["expected_input_sha256"] == sample["assets"]["png"]["sha256"] and
                not run.get("fixture_fallback", False), "INPUT_BINDING_MISMATCH")
        raw_path = asset_path(manifest.parent, sample["assets"]["png"]["path"])
        require(sha(raw_path) == run["expected_input_sha256"], "INPUT_PIN_MISMATCH")
        record_path = handoff_root / sid / "run.json"
        if record_path.exists():
            require(_read(asset_path(handoff_root, sid + "/run.json").read_bytes()) == run,
                    "RUN_REPORT_MISMATCH")
        else:
            require(run["status"] != "ok" and run.get("record_write_error") == "LOCAL_EXPORT_FAILED",
                    "MISSING_RUN_RECORD")
        signals, page, max_error = [], None, None
        if run["status"] == "ok":
            root, entry = cache[sid]
            hashes = entry["hashes"]
            objects = {}
            for key in ("ocr", "prepared", "provenance"):
                require(entry["paths"][key] == sid + "/" + key + ".json", "CACHE_PATH_MISMATCH")
                artifact = asset_path(root, entry["paths"][key])
                snapshots.append((artifact, hashes[key + "_sha256"]))
                objects[key] = _pinned(artifact, hashes[key + "_sha256"])
            page, prepared = OcrPage.from_dict(objects["ocr"]), PreparedPage.from_dict(objects["prepared"])
            page.validate_against(prepared)
            require(page.to_dict() == _read(asset_path(handoff_root, sid + "/ocr.json").read_bytes()) and
                    prepared.to_dict() == run["prepared"] ==
                    _read(asset_path(handoff_root, sid + "/prepared.json").read_bytes()), "CACHE_NATIVE_MISMATCH")
            require(page.recognition_status == run["recognition_status"] == entry["recognition_status"] and
                    page.ocr_version == run["ocr_version"] and page.artifact_version == run["artifact_version"] and
                    len(page.blocks) == run["block_count"] and len(page.unreadable_regions) == run["unreadable_count"] and
                    list(page.review_flags) == run["review_flags"] and
                    all(entry[k] == run[k] for k in ("artifact_version", "ocr_version", "block_count",
                        "unreadable_count", "review_flags")), "OCR_STATE_MISMATCH")
            profile = dict(profile=report["profile"], artifact_version=page.artifact_version,
                           ocr_version=page.ocr_version, profile_sha256=compute_profile_sha256(
                               report["profile"], artifact_version=page.artifact_version, ocr_version=page.ocr_version))
            require(profile == profiles[0], "PROFILE_PIN_MISMATCH")
            canonical = _image(asset_path(handoff_root, sid + "/canonical.png"),
                               (page.width, page.height), run["canonical"])
            declared = entry["canonical"]
            require(isinstance(declared, dict) and
                    all(type(declared.get(k)) is type(v) and declared[k] == v
                        for k, v in canonical.items()) and
                    declared.get("source_hash_recorded") is True, "CACHE_CANONICAL_MISMATCH")
            _image(asset_path(handoff_root, sid + "/processed.png"),
                   (prepared.processed.width, prepared.processed.height))
            expected = dict(input_sha256=run["expected_input_sha256"], canonical_sha256=canonical["sha256"],
                            engine_sha256=engines[0]["engine_sha256"], profile_sha256=profile["profile_sha256"])
            require(objects["provenance"] == expected and entry["provenance"] == expected and
                    all(hashes[k] == v for k, v in expected.items()), "PROVENANCE_MISMATCH")
            max_error = 0.0 if prepared.geometry_status == "available" else None
            for region in (*page.blocks, *page.unreadable_regions):
                if region.quad is None:
                    signals.append("geometry_unavailable")
                    continue
                restored = canonical_quad(processed_quad(region.quad, prepared), prepared)
                error = max(abs(a - b) * (page.width, page.height)[axis]
                            for p, q in zip(region.quad, restored) for axis, (a, b) in enumerate(zip(p, q)))
                require(error <= 1e-7, "GEOMETRY_ROUNDTRIP_MISMATCH")
                max_error = max(max_error, error)
        hypothesis = "\n".join(b.text for b in page.blocks) if page else ""
        state = page.recognition_status if page else "unavailable"
        prediction = dict(sample_id=sid, status="failed" if page is None or state == "unreadable" else "ok",
                          payload={}, ocr_text=hypothesis)
        scored = evaluate([gold_by_id[sid]], dict(artifact_version="vietdoc.predictions.v1",
            predictions=[prediction], model_version="observed-only", normalizer_version="not-applicable",
            ocr_version=page.ocr_version if page else "unavailable"))
        reference = gold_by_id[sid]["transcript"]
        if reference is not None and gold_by_id[sid]["transcript_scope"] == "full_page":
            ref, observed = text(reference), text(hypothesis)
            if ref != observed:
                signals.append("transcript_mismatch" if ref else "empty_reference_output")
                if Counter(ref.split()) == Counter(observed.split()): signals.append("word_order_only_mismatch")
                if _strip_marks(ref) == _strip_marks(observed): signals.append("diacritic_only_mismatch")
                reference_digits, observed_digits = re.findall(r"\d+", ref), re.findall(r"\d+", observed)
                if reference_digits != observed_digits:
                    signals.append("digit_order_only_mismatch" if Counter(reference_digits) == Counter(observed_digits)
                                   else "digit_content_mismatch")
        if state in ("partial", "unreadable"): signals.append("unreadable_regions")
        if page is not None and not page.blocks and not page.unreadable_regions: signals.append("no_detections")
        if run["status"] != "ok": signals.append(run.get("error_code", "EXECUTION_UNAVAILABLE"))
        row = dict(sample_id=sid, document_type=sample["document_type"], base_id=sample["base_id"],
            family_id=sample["family_id"], variant=sample["augmentation"]["name"], row_count=sample["row_count"],
            split=sample["split"], execution=run["status"], native_attempted=run["native_attempted"],
            recognition_status=state, signals=sorted(set(signals)), ocr=scored["ocr"]["all"],
            geometry_roundtrip_max_px=max_error, duration_seconds=run.get("duration_seconds"),
            memory_bytes=run.get("memory_bytes"), evidence={"native": sid + "/", "input": sample["assets"]["png"]["path"]})
        rows.append(row)
        for key in GROUPS: slices[key][str(row[key])].append(row)
    grouped = {}
    for key, values in slices.items():
        grouped[key] = {}
        for value, members in values.items():
            totals = Counter()
            for row in members: totals.update(row["ocr"]["counts"])
            grouped[key][value] = dict(samples=len(members), execution=dict(Counter(r["execution"] for r in members)),
                recognition=dict(Counter(r["recognition_status"] for r in members)),
                signals=dict(Counter(s for r in members for s in r["signals"])), ocr=_rates(totals))
    require(all(sha(path) == pin for path, pin in snapshots),
            "SOURCE_CHANGED_DURING_AUDIT")
    result = dict(artifact_version=VERSION, dataset_version=dataset_version(source), counts=counts,
        recognition=dict(Counter(r["recognition_status"] for r in rows)),
        no_detections=sum("no_detections" in r["signals"] for r in rows), samples=rows, slices=grouped,
        pins=dict(manifest_sha256=manifest_sha256, native_report_sha256=report_sha256, cache_indices=cache_pins,
                  engine_manifest=engines[0], profile=profiles[0]), data_validation=validation,
        evaluator_policy=POLICY, audit_source_sha256=sha(Path(__file__)),
        scope="PROVISIONAL exposed train/dev OCR diagnostic; not field correctness or acceptance",
        not_measured=["detection precision/recall (OCR-region matching policy not accepted)",
            "orientation/skew/crop causal attribution", "total/item mapping correctness",
            "native inference rerun, process peak/leak/hard cancellation", "model default migration"],
        engine_assurance="upstream pinned inventory from cache; this audit does not load/verify installed weights")
    output.mkdir(parents=True, exist_ok=False)
    _write(output / "report.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-root", "manifest", "handoff-root", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--index", required=True, action="append", nargs=2, metavar=("PATH", "SHA256"))
    args = parser.parse_args(argv)
    try:
        result = audit(args.data_root, args.manifest, args.manifest_sha256, args.handoff_root,
                       args.report_sha256, args.index, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print("AUDIT_INPUT_INVALID_OR_IO_ERROR", file=sys.stderr)
        return 2
    print(json.dumps(dict(counts=result["counts"], recognition=result["recognition"], no_detections=result["no_detections"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
