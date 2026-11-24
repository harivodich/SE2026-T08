"""Explicit-path tiny-set replay; provisional OCR diagnostics, not a dev baseline."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from vietdoc.contracts.ocr import OcrPage
from vietdoc.evaluation.scalar_ocr import dataset_version, evaluate_files

GROUPS = ("png", "pdf", "paired-baseline", "paired-candidate")


def _encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _read(snapshot):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    value = json.loads(snapshot.decode("utf-8"), object_pairs_hook=unique)
    # Reject nonfinite numbers (including overflow) and lone surrogates anywhere.
    _encode(value)
    return value


def _write(path, value):
    encoded = _encode(value)
    with path.open("xb") as stream:
        stream.write(encoded)


def replay(data_root, manifest_path, expected_hash, input_root, output_dir, groups):
    data_root, input_root, output_dir = (Path(p).resolve() for p in (data_root, input_root, output_dir))
    manifest_path = Path(manifest_path)
    manifest_path = (manifest_path if manifest_path.is_absolute() else data_root / manifest_path).resolve()
    if not manifest_path.is_relative_to(data_root):
        raise ValueError("MANIFEST_OUTSIDE_DATA_ROOT")
    snapshot = manifest_path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or sha256(snapshot).hexdigest() != expected_hash:
        raise ValueError("MANIFEST_HASH_MISMATCH")
    manifest = _read(snapshot)
    if not groups or len(groups) != len(set(groups)) or any(g not in GROUPS for g in groups):
        raise ValueError("INVALID_GROUPS")
    plans = []
    for name in groups:
        records, pins, versions = [], {}, set()
        for sample in manifest["samples"]:
            sid = sample["sample_id"]
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", sid) or sid in pins:
                raise ValueError("INVALID_SAMPLE_ID")
            folder = {"png": ("native", sid + "-measured-1"),
                      "pdf": ("native", sid + "-pdf-proposal-0"),
                      "paired-baseline": ("paired", sid + "-baseline"),
                      "paired-candidate": ("paired", sid + "-candidate")}[name]
            path = input_root.joinpath(*folder, "ocr.json").resolve()
            if not path.is_relative_to(input_root):
                raise ValueError("OCR_INPUT_OUTSIDE_ROOT")
            data = path.read_bytes()
            page = OcrPage.from_dict(_read(data))
            pins[sid] = sha256(data).hexdigest()
            versions.add(page.ocr_version)
            # Never copy business gold into an OCR-only diagnostic prediction.
            record = {"sample_id": sid,
                      "status": "failed" if page.recognition_status == "unreadable" else "ok",
                      "payload": {}, "ocr_text": "\n".join(b.text for b in page.blocks),
                      "ocr_diagnostics": {**page.to_dict(), "artifact_version": page.artifact_version,
                          "recognition_status": page.recognition_status, "review_flags": list(page.review_flags)}}
            if record["status"] == "failed":
                record["error"] = "OCR_UNREADABLE_REGIONS"
            records.append(record)
        if len(versions) != 1:
            raise ValueError("OCR_VERSION_MISMATCH")
        plans.append((name, {"artifact_version": "vietdoc.predictions.v1",
            "dataset_manifest_sha256": expected_hash, "dataset_version": dataset_version(manifest),
            "model_version": "ppocrv5-det-tess-vie-diagnostic",
            "normalizer_version": "ocr-only-no-business-normalizer", "ocr_version": versions.pop(),
            "predictions": records, "source_ocr_sha256": pins, "business_metrics_applicable": False,
            "diagnostic_status": "PROVISIONAL: tiny integration set; reading-order protocol not accepted"}))
    # All requested OCR inputs and the declared manifest hash pass before output.
    for _, artifact in plans:
        _encode(artifact)
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, artifact in plans:
        directory = output_dir / ("diagnostic-" + name)
        directory.mkdir()
        prediction_path = directory / "predictions.json"
        _write(prediction_path, artifact)
        report = evaluate_files(data_root, manifest_path, prediction_path)
        report["diagnostic_status"] = artifact["diagnostic_status"]
        report["business_metrics_applicable"] = False
        report["source_ocr_states"] = {r["sample_id"]: {k: r["ocr_diagnostics"][k]
            for k in ("artifact_version", "recognition_status", "review_flags")}
            for r in artifact["predictions"]}
        _write(directory / "report.json", report)
        print(name, json.dumps({k: {m: v[m] for m in ("cer", "wer")} for k, v in report["ocr"].items()}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path, help="Absolute path or relative to --data-root")
    parser.add_argument("--manifest-sha256", required=True, help="Expected hash from the handed-off manifest pin")
    parser.add_argument("--input-root", required=True, type=Path, help="Existing native/ and/or paired/ artifacts")
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory; never overwritten")
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=["png", "pdf"])
    args = parser.parse_args(argv)
    try:
        replay(args.data_root, args.manifest, args.manifest_sha256, args.input_root, args.output_dir, args.groups)
    except FileExistsError:
        print("OUTPUT_EXISTS", file=sys.stderr)
        return 2
    except OSError:
        print("REPLAY_IO_ERROR", file=sys.stderr)
        return 2
    except (ValueError, KeyError, TypeError, RecursionError):
        print("REPLAY_INPUT_INVALID", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
