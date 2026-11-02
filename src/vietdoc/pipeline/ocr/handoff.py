"""Offline D1 OCR handoff example; no service attempt writer or business state.

The caller owns the loaded engine. Serialize pixels inside recognize_document;
hash encoded canonical bytes, keep every requested sample in the report, and
never pass transcript/gold into inference. Output directories must be new.
"""

from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import platform
import re
import time

from vietdoc.contracts.ocr import OcrPage
from vietdoc.pipeline.evidence import EVIDENCE_VERSION
from vietdoc.pipeline.geometry import GEOMETRY_VERSION
from vietdoc.pipeline.ocr import OCR_STAGE_VERSION, OcrError, recognize_document
from vietdoc.pipeline.preprocess import PreprocessError, PreprocessLimits


def _json(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def _asset(root, asset):
    if not isinstance(asset, dict) or not isinstance(asset.get("path"), str):
        raise ValueError("Invalid manifest asset")
    relative = PurePosixPath(asset["path"])
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or any("\\" in p or ":" in p for p in relative.parts):
        raise ValueError("Asset must remain under the repository root")
    if not isinstance(asset.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
        raise ValueError("Asset must declare an exact SHA-256")
    path = root.joinpath(*relative.parts)
    path.resolve().relative_to(root)
    return path


def _memory():
    try:
        import psutil
        value = psutil.Process().memory_info()
        return {name: getattr(value, name) for name in ("rss", "private", "peak_wset") if hasattr(value, name)}
    except ImportError:
        return None


def review_manifest(root, manifest_path, output_dir, engine, *, sample_ids=None,
                    limits=None, remaining_budget_ms=180_000, fixture_fallback=False):
    """Write local review outputs, not runtime storage or consumer acceptance.

    Tiny-fixture fallback is opt-in and still uses the manifest's exact hash.
    Missing assets are NOT_RUN handoff failures, never fabricated native calls.
    """
    from vietdoc.pipeline.ocr.paddle_adapter import draw_overlay
    from vietdoc.pipeline.ocr.preview import render_preview

    root, manifest_path, output_dir = Path(root).resolve(), Path(manifest_path), Path(output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = manifest.get("samples") if isinstance(manifest, dict) else None
    if not isinstance(samples, list) or not samples or len(samples) > 20:
        raise ValueError("Expected 1..20 D1 integration samples")
    ids = [sample.get("sample_id") if isinstance(sample, dict) else None for sample in samples]
    if any(not isinstance(s, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", s) for s in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid or duplicate Data sample IDs")
    if sample_ids is not None and (not sample_ids or len(sample_ids) != len(set(sample_ids)) or set(sample_ids) - set(ids)):
        raise ValueError("Requested IDs must be unique and declared in the manifest")
    selected = [sample for sample in samples if sample_ids is None or sample["sample_id"] in sample_ids]
    for sample in selected:
        if sample.get("document_type") not in ("receipt", "invoice"):
            raise ValueError("Only receipt/invoice handoff is supported")
        assets = sample.get("assets")
        _asset(root, assets.get("png") if isinstance(assets, dict) else None)
    limits = PreprocessLimits() if limits is None else limits
    output_dir.mkdir(parents=True, exist_ok=False)
    report = {"kind": "offline D1 OCR handoff; not evaluator or consumer acceptance",
              "manifest_version": manifest.get("version"), "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
              "provider": type(engine).__name__, "python": platform.python_version(), "hardware": platform.platform(),
              "engine_load_seconds": getattr(engine, "load_seconds", None),
              "font_sha256": manifest.get("font_sha256"), "config_sha256": manifest.get("config_sha256"),
              "versions": {"stage": OCR_STAGE_VERSION, "geometry": GEOMETRY_VERSION, "evidence": EVIDENCE_VERSION,
                           "Pillow": version("Pillow"), "pypdfium2": version("pypdfium2")},
              "profile": {"processed_long_edge": limits.processed_long_edge, "pdf_dpi": limits.pdf_dpi,
                          "max_pixels": limits.max_pixels, "budget_ms": remaining_budget_ms},
              "consumer_acceptance": "pending AI2/Backend; local parser check only", "samples": []}
    for sample in selected:
        started, stage = time.monotonic(), "input_handoff"
        sample_id, asset = sample["sample_id"], sample["assets"]["png"]
        path = _asset(root, asset)
        fallback = False
        if not path.is_file() and fixture_fallback:
            path = root / "tests/fixtures/d12" / (sample_id + ".png")
            path.resolve().relative_to(root)
            fallback = True
        case = {"sample_id": sample_id, "document_type": sample["document_type"],
                "input_declared_path": asset["path"], "fixture_fallback": fallback,
                "expected_input_sha256": asset["sha256"], "native_attempted": False}
        target = output_dir / sample_id
        target.mkdir()

        class ObservedEngine:
            def recognize(self, loaded, *, remaining_budget_ms):
                case["native_attempted"] = True
                return engine.recognize(loaded, remaining_budget_ms=remaining_budget_ms)

        try:
            with path.open("rb") as stream:
                data = stream.read(limits.max_file_bytes + 1)
            stage = "preprocess_ocr"
            with recognize_document(data, ObservedEngine(), limits=limits, remaining_budget_ms=remaining_budget_ms,
                                    expected_sha256=asset["sha256"]) as result:
                stage = "local_export"
                loaded, page = result.loaded, result.ocr
                with BytesIO() as encoded:
                    loaded.canonical.save(encoded, format="PNG")
                    canonical = encoded.getvalue()
                (target / "canonical.png").write_bytes(canonical)
                loaded.processed.save(target / "processed.png")
                _json(target / "ocr.json", page.to_dict())
                _json(target / "prepared.json", loaded.metadata.to_dict())
                with draw_overlay(loaded.canonical, page) as overlay:
                    overlay.save(target / "overlay.png")
                (target / "preview.html").write_text(render_preview(loaded.canonical, page), encoding="utf-8")
                parsed = OcrPage.from_dict(json.loads((target / "ocr.json").read_text(encoding="utf-8")))
                parsed.validate_against(loaded.metadata)
                case.update(status="ok", recognition_status=page.recognition_status, artifact_version=page.artifact_version,
                            ocr_version=page.ocr_version, input_sha256=loaded.input_sha256,
                            canonical={"width": page.width, "height": page.height, "sha256": sha256(canonical).hexdigest(),
                                       "size_bytes": len(canonical),
                                       "rgb_pixel_sha256": sha256(loaded.canonical.tobytes()).hexdigest()},
                            prepared=loaded.metadata.to_dict(), block_count=len(page.blocks),
                            unreadable_count=len(page.unreadable_regions), review_flags=list(page.review_flags),
                            ocr_seconds=getattr(engine, "last_inference_seconds", None), memory_bytes=_memory(),
                            local_consumer_parse="passed; not AI2/Backend acceptance")
        except FileNotFoundError:
            case.update(status="not_run" if stage == "input_handoff" else "failed", stage=stage,
                        error_code="INPUT_ARTIFACT_UNAVAILABLE" if stage == "input_handoff" else "LOCAL_EXPORT_FAILED")
        except (OcrError, PreprocessError) as exc:
            case.update(status="failed", stage=stage, error_code=exc.code)
        except OSError:
            case.update(status="failed", stage=stage, error_code="LOCAL_IO_ERROR")
        except MemoryError:
            case.update(status="failed", stage=stage, error_code="LOCAL_MEMORY_EXHAUSTED")
        case["duration_seconds"] = time.monotonic() - started
        report["samples"].append(case)
        _json(target / "run.json", case)
    report["counts"] = {"requested": len(selected), "native_attempted": sum(c["native_attempted"] for c in report["samples"]),
                        **{s: sum(c["status"] == s for c in report["samples"]) for s in ("ok", "failed", "not_run")}}
    _json(output_dir / "report.json", report)
    return report


def main():
    import argparse
    from vietdoc.pipeline.ocr.paddle_adapter import VietnameseOcrEngine

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--sample-ids", nargs="+")
    parser.add_argument("--fixture-fallback", action="store_true")
    parser.add_argument("--artifact-version", type=int, choices=(1,2), default=1)
    args = parser.parse_args()
    engine = VietnameseOcrEngine(args.model_root, artifact_version=args.artifact_version)
    try:
        engine.load()
        report = review_manifest(args.root, args.manifest, args.output_dir, engine,
                                 sample_ids=args.sample_ids, fixture_fallback=args.fixture_fallback)
        print(json.dumps(report["counts"]))
        return 0 if report["counts"]["ok"] == report["counts"]["requested"] else 2
    except OcrError as exc:
        print(json.dumps({"code": exc.code, "stage": "engine_load"}))
        return 2
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
