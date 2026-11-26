"""Build a pinned development case ledger from observed OCR; never infer or repair text."""
import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PIL import Image, __version__ as pillow_version

from vietdoc.contracts.ocr import OcrPage
from vietdoc.data.manifest import asset_path, require, sha
from vietdoc.pipeline.ocr.audit import audit, _pinned
from vietdoc.pipeline.ocr.diagnose import _read, _write
from vietdoc.pipeline.ocr.paddle_adapter import draw_overlay


def _verify_overlay(root, sid, canonical_pin, ocr, snapshots):
    """Bind the referenced overlay pixels to the pinned canonical and OCR page.

    Compare decoded RGB pixels, not PNG encoding: metadata/compression may vary.
    Read bounded snapshots and rehash their paths before publishing the ledger.
    """
    page = OcrPage.from_dict(ocr)
    images = {}
    for name in ("canonical", "overlay"):
        path = asset_path(root, sid + "/" + name + ".png")
        with path.open("rb") as stream:
            raw = stream.read(20 * 1024 * 1024 + 1)
        require(0 < len(raw) <= 20 * 1024 * 1024, "TRIAGE_IMAGE_BYTE_CAP")
        digest = sha256(raw).hexdigest()
        if name == "canonical":
            require(digest == canonical_pin["sha256"], "CANONICAL_PIN_MISMATCH")
        snapshots.append((path, digest))
        images[name] = raw
    with Image.open(BytesIO(images["canonical"]), formats=("PNG",)) as canonical, \
            Image.open(BytesIO(images["overlay"]), formats=("PNG",)) as overlay:
        require(all(im.mode == "RGB" and im.size == (page.width, page.height) and im.n_frames == 1
                    for im in (canonical, overlay)) and page.width * page.height <= 20_000_000,
                "OVERLAY_FRAME_MISMATCH")
        with draw_overlay(canonical, page) as expected:
            pixel_hash = sha256(overlay.tobytes()).hexdigest()
            require(pixel_hash == sha256(expected.tobytes()).hexdigest(), "OVERLAY_CONTENT_MISMATCH")
    return dict(sha256=sha256(images["overlay"]).hexdigest(), size_bytes=len(images["overlay"]),
                rgb_pixel_sha256=pixel_hash, width=page.width, height=page.height,
                method="draw_overlay-rgb-exact.v1", pillow_version=pillow_version,
                renderer_source_sha256=sha(Path(__file__).with_name("paddle_adapter.py")))


def build_ledger(*, sample_ids, **audit_options):
    """Audit the full population, then export an explicitly selected dev subset.

    Annotation regions and OCR blocks are separate arrays: no positional matching,
    detection recall claim, gold filling or automatic causal classification.
    """
    require(isinstance(sample_ids, (list, tuple)) and 8 <= len(sample_ids) <= 12
            and all(isinstance(s, str) for s in sample_ids)
            and len(set(sample_ids)) == len(sample_ids), "INVALID_TRIAGE_SELECTION")
    output = Path(audit_options["output_dir"])
    require(not output.exists(), "OUTPUT_EXISTS")
    manifest = Path(audit_options["manifest"])
    source = _pinned(manifest, audit_options["manifest_sha256"])
    samples = {s["sample_id"]: s for s in source["samples"]}
    require(all(s in samples and samples[s]["split"] == "dev" for s in sample_ids),
            "TRIAGE_REQUIRES_EXPOSED_DEV")
    selected = [samples[s] for s in sample_ids]
    require({s["document_type"] for s in selected} == {"receipt", "invoice"}
            and {"clean", "mild", "crop", "unreadable"} <= {s["augmentation"]["name"] for s in selected}
            and {0, 12, 30} <= {s["row_count"] for s in selected}, "TRIAGE_COVERAGE_MISSING")
    # Temporary output stays beside the target. Publish only the complete packet;
    # a bad cache/report/annotation leaves no successful output directory.
    with TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / "packet"
        verified = audit(**{**audit_options, "output_dir": staging})
        report = _pinned(Path(audit_options["handoff_root"]) / "report.json", audit_options["report_sha256"])
        native = {r["sample_id"]: r for r in report["samples"]}
        rows = {r["sample_id"]: r for r in verified["samples"]}
        ledger, snapshots = [], []
        for sid in sample_ids:
            sample, run, row = samples[sid], native[sid], rows[sid]
            annotation = {}
            for key in ("txt", "regions.json"):
                asset = sample["assets"][key]
                path = asset_path(manifest.parent, asset["path"])
                snapshot = path.read_bytes()
                require(sha256(snapshot).hexdigest() == asset["sha256"], "ANNOTATION_PIN_MISMATCH")
                snapshots.append((path, asset["sha256"]))
                annotation[key] = snapshot.decode("utf-8") if key == "txt" else _read(snapshot)
            ocr, overlay_verification = None, None
            if run["status"] == "ok":
                path = asset_path(Path(audit_options["handoff_root"]), sid + "/ocr.json")
                # The full audit already validated the typed page/cache. Bind the
                # readback to that same pinned cache entry before copying it.
                entries = [_pinned(Path(p), pin)["samples"].get(sid) for p, pin in audit_options["indices"]]
                entry = next(e for e in entries if e is not None)
                ocr = _pinned(path, entry["hashes"]["ocr_sha256"])
                snapshots.append((path, entry["hashes"]["ocr_sha256"]))
                overlay_verification = _verify_overlay(Path(audit_options["handoff_root"]), sid,
                                                       run["canonical"], ocr, snapshots)
            ledger.append(dict(
                **{k: row[k] for k in ("sample_id", "document_type", "base_id", "family_id", "variant",
                                       "row_count", "split", "execution", "recognition_status", "signals", "ocr")},
                source_sha256=run["expected_input_sha256"], canonical=run.get("canonical"),
                expected=dict(transcript=annotation["txt"], regions=annotation["regions.json"],
                              authority="pinned Data annotation; renderer-local geometry, not accepted matching policy"),
                observed=ocr,
                overlay_verification=overlay_verification,
                evidence=dict(input=sample["assets"]["png"]["path"],
                              canonical=sid + "/canonical.png" if ocr is not None else None,
                              overlay=sid + "/overlay.png" if ocr is not None else None,
                              processed=sid + "/processed.png" if ocr is not None else None),
                diagnosis=dict(stage="unknown", certainty="unclassified",
                               impact="requires case review; aggregate CER is not causal evidence",
                               next_check="inspect source/processed pixels and region identity; distinguish detection, recognition, order/evidence and extraction",
                               conclusion="not established by this exporter")))
        require(all(sha(p) == pin for p, pin in snapshots)
                and sha(manifest) == audit_options["manifest_sha256"]
                and sha(Path(audit_options["handoff_root"]) / "report.json") == audit_options["report_sha256"],
                "SOURCE_CHANGED_DURING_TRIAGE")
        result = dict(artifact_version="vietdoc.ocr-triage.v1", scope="development case review, not acceptance",
                      sample_ids=list(sample_ids), pins=verified["pins"], evaluator_policy=verified["evaluator_policy"],
                      triage_source_sha256=sha(Path(__file__)), cases=ledger,
                      roots=dict(input="relative to manifest parent", evidence="relative to handoff root"),
                      limitations=["no region pairing or detection metric", "no causal stage claims",
                                   "no inference or model change", "oracle protocol remains Proposed"])
        _write(staging / "triage.json", result)
        require(not output.exists(), "OUTPUT_EXISTS")
        staging.rename(output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-root", "manifest", "handoff-root", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("manifest-sha256", "report-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--index", required=True, action="append", nargs=2, dest="indices", metavar=("PATH", "SHA256"))
    parser.add_argument("--sample-id", required=True, action="append", dest="sample_ids")
    args = vars(parser.parse_args(argv))
    try:
        result = build_ledger(**args)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print("TRIAGE_INPUT_INVALID_OR_IO_ERROR", file=sys.stderr)
        return 2
    print(f"TRIAGE_WRITTEN cases={len(result['cases'])}; causal diagnosis pending review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
