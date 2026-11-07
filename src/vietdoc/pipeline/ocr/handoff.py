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


HANDOFF_REPORT_VERSION = "vietdoc.ocr-handoff.v2"


class HandoffError(ValueError):
    """Safe local CLI/storage error; never includes exception text or paths."""

    def __init__(self, code, stage):
        self.code, self.stage = code, stage
        super().__init__(code)


def _io_code(stage):
    return {"input": "LOCAL_INPUT_IO_ERROR", "preprocess": "LOCAL_PREPROCESS_IO_ERROR",
            "ocr": "LOCAL_OCR_IO_ERROR", "export": "LOCAL_EXPORT_FAILED"}[stage]


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
    # Portable output identity: aliases collide on Windows, even on a Linux run.
    # Detect before creating any directory; preserve the original IDs verbatim.
    if len({sample_id.casefold() for sample_id in ids}) != len(ids):
        raise ValueError("Data sample IDs alias the same output path")
    if sample_ids is not None and (not sample_ids or len(sample_ids) != len(set(sample_ids)) or set(sample_ids) - set(ids)):
        raise ValueError("Requested IDs must be unique and declared in the manifest")
    selected = [sample for sample in samples if sample_ids is None or sample["sample_id"] in sample_ids]
    for sample in selected:
        if sample.get("document_type") not in ("receipt", "invoice"):
            raise ValueError("Only receipt/invoice handoff is supported")
        assets = sample.get("assets")
        _asset(root, assets.get("png") if isinstance(assets, dict) else None)
    limits = PreprocessLimits() if limits is None else limits
    report = {"kind": "offline D1 OCR handoff; not evaluator or consumer acceptance",
              "report_version": HANDOFF_REPORT_VERSION, "run_status": "completed", "abort_code": None,
              "manifest_version": manifest.get("version"), "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
              "provider": type(engine).__name__, "python": platform.python_version(), "hardware": platform.platform(),
              "engine_load_seconds": getattr(engine, "load_seconds", None),
              "font_sha256": manifest.get("font_sha256"), "config_sha256": manifest.get("config_sha256"),
              "versions": {"stage": OCR_STAGE_VERSION, "geometry": GEOMETRY_VERSION, "evidence": EVIDENCE_VERSION,
                           "Pillow": version("Pillow"), "pypdfium2": version("pypdfium2")},
              "profile": {"processed_long_edge": limits.processed_long_edge, "pdf_dpi": limits.pdf_dpi,
                          "max_pixels": limits.max_pixels, "budget_ms": remaining_budget_ms},
              "consumer_acceptance": "pending AI2/Backend; local parser check only", "samples": []}
    plans = []
    for sample in selected:
        sample_id, asset = sample["sample_id"], sample["assets"]["png"]
        path = _asset(root, asset)
        fallback = False
        if not path.is_file() and fixture_fallback:
            path = root / "tests/fixtures/d12" / (sample_id + ".png")
            path.resolve().relative_to(root)
            fallback = True
        case = {"sample_id": sample_id, "document_type": sample["document_type"],
                "input_declared_path": asset["path"], "fixture_fallback": fallback,
                "expected_input_sha256": asset["sha256"], "native_attempted": False,
                "status": "not_run", "stage": "not_started", "error_code": "BATCH_ABORTED",
                "duration_seconds": 0.0}
        report["samples"].append(case)
        plans.append((case, path))
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except OSError:
        raise HandoffError("OUTPUT_DIRECTORY_UNAVAILABLE", "export") from None
    for case, path in plans:
        started = time.monotonic()
        case.pop("error_code")
        target = output_dir / case["sample_id"]

        class ObservedEngine:
            def recognize(self, loaded, *, remaining_budget_ms):
                case["native_attempted"] = True
                case["stage"] = "ocr"
                return engine.recognize(loaded, remaining_budget_ms=remaining_budget_ms)

        try:
            case["stage"] = "export"
            target.mkdir()
            case["stage"] = "input"
            with path.open("rb") as stream:
                data = stream.read(limits.max_file_bytes + 1)
            case["stage"] = "preprocess"
            with recognize_document(data, ObservedEngine(), limits=limits, remaining_budget_ms=remaining_budget_ms,
                                    expected_sha256=case["expected_input_sha256"]) as result:
                case["stage"] = "export"
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
            missing_input = case["stage"] == "input"
            case.update(status="not_run" if missing_input else "failed",
                        error_code="INPUT_ARTIFACT_UNAVAILABLE" if missing_input else _io_code(case["stage"]))
        except (OcrError, PreprocessError) as exc:
            case.update(status="failed", error_code=exc.code)
        except OSError:
            case.update(status="failed", error_code=_io_code(case["stage"]))
        except Exception as exc:
            code = "LOCAL_MEMORY_EXHAUSTED" if isinstance(exc, MemoryError) else "UNEXPECTED_FAILURE"
            case.update(status="failed", error_code=code)
            report.update(run_status="aborted", abort_code=code)
        case["duration_seconds"] = time.monotonic() - started
        try:
            _json(target / "run.json", case)
        except OSError:
            case["record_write_error"] = "LOCAL_EXPORT_FAILED"
            if case["status"] == "ok":
                case.update(status="failed", stage="export", error_code="LOCAL_EXPORT_FAILED")
        except Exception:
            case.update(status="failed", stage="export", error_code="UNEXPECTED_FAILURE")
            report.update(run_status="aborted", abort_code="UNEXPECTED_FAILURE")
        if report["run_status"] == "aborted":
            break
    report["counts"] = {"requested": len(selected), "native_attempted": sum(c["native_attempted"] for c in report["samples"]),
                        **{s: sum(c["status"] == s for c in report["samples"]) for s in ("ok", "failed", "not_run")}}
    try:
        _json(output_dir / "report.json", report)
    except Exception:
        raise HandoffError("LOCAL_REPORT_WRITE_FAILED", "export") from None
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
    engine, stage, report_written = None, "engine_load", False
    try:
        engine = VietnameseOcrEngine(args.model_root, artifact_version=args.artifact_version)
        engine.load()
        stage = "input"
        report = review_manifest(args.root, args.manifest, args.output_dir, engine,
                                 sample_ids=args.sample_ids, fixture_fallback=args.fixture_fallback)
        report_written = True
        payload = {"counts": report["counts"], "run_status": report["run_status"], "report_written": True}
        status = 0 if report["run_status"] == "completed" and report["counts"]["ok"] == report["counts"]["requested"] else 2
    except HandoffError as exc:
        payload, status = {"code": exc.code, "stage": exc.stage, "report_written": False}, 2
    except (OcrError, PreprocessError) as exc:
        payload, status = {"code": exc.code, "stage": stage, "report_written": False}, 2
    except ValueError:
        payload, status = {"code": "MANIFEST_INVALID" if stage == "input" else "ENGINE_SETUP_FAILED",
                           "stage": stage, "report_written": False}, 2
    except Exception:
        payload, status = {"code": "UNEXPECTED_FAILURE", "stage": stage, "report_written": False}, 2
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception:
                payload, status = {"code": "ENGINE_CLOSE_FAILED", "stage": "engine_close",
                                   "report_written": report_written}, 2
    print(json.dumps(payload))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
