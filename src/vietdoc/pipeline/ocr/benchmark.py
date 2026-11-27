"""Bounded native OCR resource probe: one cold request and 10 x 3 warm requests.

This offline probe holds one engine slot, never provisions models, and reports
sampled process-tree RSS. Its 30 warm observations are not a production SLA.
"""
import argparse
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
from threading import Event, Thread
import time

from vietdoc.data.manifest import require, sha
from vietdoc.pipeline.ocr import OcrError
from vietdoc.pipeline.ocr.diagnose import _write
from vietdoc.pipeline.ocr.handoff import _prepare_manifest
from vietdoc.pipeline.ocr.paddle_adapter import (MODEL_SET_ID, MODELS, OCR_VERSION,
    RUNTIME_VERSIONS, VietnameseOcrEngine, _verify_model)
from vietdoc.pipeline.preprocess import PreprocessError, PreprocessLimits, load_document


def membership_hash(ids):
    return sha256(("\n".join(sorted(ids)) + "\n").encode("utf-8")).hexdigest()


class _MemorySampler:
    def __init__(self, interval=0.05):
        import psutil

        self.process = psutil.Process(os.getpid())
        self.interval = interval
        self.started = time.monotonic()
        self.samples = []
        self.stop = Event()
        self.thread = Thread(target=self._loop, daemon=True)

    def current(self):
        import psutil

        members = [self.process]
        try:
            members += self.process.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        rss, seen = 0, 0
        for process in members:
            try:
                rss += process.memory_info().rss
                seen += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return dict(rss_bytes=rss, process_count=seen)

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.samples.append(dict(t_seconds=time.monotonic() - self.started, **self.current()))
            except Exception:
                # Sampling gaps are reported through the raw count/interval.
                pass
            self.stop.wait(self.interval)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=2)
        self.samples.append(dict(t_seconds=time.monotonic() - self.started, **self.current()))


def _observation(sid, path, expected_hash, engine, limits, phase, repeat, sampler):
    started = time.monotonic()
    deadline = started + 180
    record = dict(sample_id=sid, phase=phase, repeat=repeat, status="not_run",
                  input_sha256=expected_hash, stage_seconds={}, process_tree_rss_before=sampler.current())
    try:
        with path.open("rb") as stream:
            source = stream.read(limits.max_file_bytes + 1)
        require(0 < len(source) <= limits.max_file_bytes and sha256(source).hexdigest() == expected_hash,
                "INPUT_PIN_OR_BYTE_CAP_MISMATCH")
        before_decode = time.monotonic()
        with load_document(source, limits=limits,
                           remaining_budget_ms=max(0, int((deadline - time.monotonic()) * 1000)),
                           expected_sha256=expected_hash) as loaded:
            before_ocr = time.monotonic()
            page = engine.recognize(loaded,
                                    remaining_budget_ms=max(0, int((deadline - time.monotonic()) * 1000)))
            before_serialize = time.monotonic()
            encoded = json.dumps(page.to_dict(), ensure_ascii=False, allow_nan=False).encode("utf-8")
            after_serialize = time.monotonic()
            record.update(status="ok", recognition_status=page.recognition_status,
                          block_count=len(page.blocks), unreadable_count=len(page.unreadable_regions),
                          canonical_size=list(loaded.canonical.size),
                          canonical_rgb_sha256=sha256(loaded.canonical.tobytes()).hexdigest(),
                          ocr_sha256=sha256(encoded).hexdigest())
        after_cleanup = time.monotonic()
        record["stage_seconds"] = dict(input=before_decode - started,
            preprocess=before_ocr - before_decode, ocr=before_serialize - before_ocr,
            serialize=after_serialize - before_serialize,
            postprocess_cleanup=after_cleanup - after_serialize)
    except (OcrError, PreprocessError) as exc:
        record.update(status="failed", error_code=exc.code)
    except (OSError, ValueError, TypeError, MemoryError):
        record.update(status="failed", error_code="LOCAL_BENCHMARK_FAILURE")
    record["duration_seconds"] = time.monotonic() - started
    record["process_tree_rss_after"] = sampler.current()
    return record


def benchmark(*, root, manifest, manifest_sha256, model_root, sample_ids,
              membership_sha256, output_dir):
    """Preflight exact dev10 membership before loading the pinned native model."""
    root, manifest, model_root, output = map(Path, (root, manifest, model_root, output_dir))
    require(not output.exists(), "OUTPUT_EXISTS")
    require(len(sample_ids) == 10 and len(set(sample_ids)) == 10 and
            membership_hash(sample_ids) == membership_sha256, "BENCHMARK_MEMBERSHIP_MISMATCH")
    plan = _prepare_manifest(root, manifest, sample_ids=sample_ids, max_manifest_samples=200)
    source, observed_manifest_hash, selected = plan
    require(observed_manifest_hash == manifest_sha256 and len(selected) == 10,
            "BENCHMARK_MANIFEST_MISMATCH")
    by_id = {sample["sample_id"]: sample for sample in source["samples"]}
    require(all(by_id[sid]["split"] == "dev" for sid in sample_ids) and
            {(by_id[sid]["document_type"], by_id[sid]["row_count"]) for sid in sample_ids} ==
            {(kind, count) for kind in ("receipt", "invoice") for count in (0, 1, 3, 12, 30)},
            "BENCHMARK_COVERAGE_MISMATCH")
    paths = {case["sample_id"]: (case, path) for case, path in selected}
    require(all(path.is_file() and sha(path) == case["expected_input_sha256"]
                for case, path in paths.values()), "BENCHMARK_INPUT_PIN_MISMATCH")
    limits = PreprocessLimits()
    engine = VietnameseOcrEngine(model_root, artifact_version=2)
    adapter_path = Path(__file__).with_name("paddle_adapter.py")
    adapter_pin, benchmark_pin = sha(adapter_path), sha(Path(__file__))
    import psutil

    observations = []
    status, error_code = "completed", None
    with _MemorySampler() as sampler:
        before_load = sampler.current()
        started = time.monotonic()
        try:
            engine.load()
            load_seconds = time.monotonic() - started
            after_load = sampler.current()
            first = sample_ids[0]
            case, path = paths[first]
            observations.append(_observation(first, path, case["expected_input_sha256"],
                                             engine, limits, "cold_request", 0, sampler))
            after_cold = sampler.current()
            for repeat in range(1, 4):
                for sid in sample_ids:
                    case, path = paths[sid]
                    observations.append(_observation(sid, path, case["expected_input_sha256"],
                                                     engine, limits, "warm", repeat, sampler))
            if any(record["status"] != "ok" for record in observations):
                status, error_code = "failed", "OBSERVATION_FAILED"
        except OcrError as exc:
            status, error_code = "failed", exc.code
            load_seconds = None
            after_load = None
            after_cold = None
        finally:
            try:
                engine.close()
            except OcrError as exc:
                status, error_code = "failed", exc.code
        after_close = sampler.current()
    for name, spec in MODELS.items():
        _verify_model(engine.model_root / (name + "_infer"), spec)
    require(sha(adapter_path) == adapter_pin and sha(Path(__file__)) == benchmark_pin,
            "BENCHMARK_SOURCE_CHANGED")
    report = dict(artifact_version="vietdoc.ocr-native-benchmark.v1", status=status,
                  error_code=error_code, manifest_sha256=manifest_sha256,
                  membership_sha256=membership_sha256, sample_ids=list(sample_ids),
                  model_set_id=MODEL_SET_ID, ocr_version=OCR_VERSION,
                  model_files={name: {file: dict(sha256=sha(engine.model_root / (name + "_infer") / file),
                                                  size_bytes=(engine.model_root / (name + "_infer") / file).stat().st_size)
                                           for file in spec["files"]} for name, spec in MODELS.items()},
                  runtime_versions={name: version(name) for name in RUNTIME_VERSIONS},
                  adapter_source_sha256=adapter_pin,
                  benchmark_source_sha256=benchmark_pin,
                  platform=platform.platform(), python=platform.python_version(),
                  cpu_count=os.cpu_count(), logical_threads_at_end=psutil.Process().num_threads(),
                  total_memory_bytes=psutil.virtual_memory().total,
                  profile=dict(processed_long_edge=limits.processed_long_edge, pdf_dpi=limits.pdf_dpi,
                               max_file_bytes=limits.max_file_bytes, max_pixels=limits.max_pixels,
                               timeout_seconds=limits.timeout_seconds, budget_ms=180000),
                  load_seconds=load_seconds, memory=dict(before_load=before_load,
                      after_load=after_load, after_cold=after_cold, after_close=after_close,
                      sample_interval_seconds=sampler.interval, raw_samples=sampler.samples,
                      sampled_peak_tree_rss_bytes=max((s["rss_bytes"] for s in sampler.samples), default=None)),
                  observations=observations,
                  limitations=["sampled process-tree RSS may miss short peaks",
                               "one cold request plus 30 warm observations is not a production SLA",
                               "native detector and recognizer substage timings are not instrumented"])
    require(sha(manifest) == manifest_sha256 and all(sha(path) == case["expected_input_sha256"]
            for case, path in paths.values()), "BENCHMARK_SOURCE_CHANGED")
    output.mkdir(parents=True, exist_ok=False)
    _write(output / "benchmark.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "manifest", "model-root", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--membership-sha256", required=True)
    parser.add_argument("--sample-id", required=True, action="append", dest="sample_ids")
    try:
        result = benchmark(**vars(parser.parse_args(argv)))
    except (OSError, ValueError, KeyError, TypeError):
        print("NATIVE_BENCHMARK_INVALID_OR_IO_ERROR", file=sys.stderr)
        return 2
    print(json.dumps(dict(status=result["status"], error_code=result["error_code"],
                          observations=len(result["observations"]))))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
