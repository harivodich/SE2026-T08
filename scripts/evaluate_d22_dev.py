#!/usr/bin/env python3
"""Reproducible OFFLINE B0/M0/M1 D22 dev inference and separate gold scoring."""

from __future__ import annotations

import argparse
import importlib.metadata
import logging
import math
import os
import platform
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

CONTEXT_ID = "657a7737c4b65fbfcfc44b22e806ca23f87e3f14357813bac6a9eb3085a75f12"
MANIFEST_SHA = "eaabf08f5511de0db7bfdf9b7f087716cd0acf197bb00bca9fcb34341f8314db"
RUN_SHA = "5888ddf148d1f74c99b9968b68a66059ba6dc4e107cd217ef2a0019de9a1e907"
CHECKPOINT_SHA = "eb8ceaec95985c26951c00cc4fe1b69b8d7efded0b1765a0ba629550b8cce268"
CONFIG_SHA = "8a30055732d10ca5277a4654dd7c616d15c8ffed764999a7304e3d65e7be6f0e"
PREFLIGHT_SHA = "9ec4bdc4819eee672f748367765958dcfa8781c4c1583a2c48d3b29ea52a5818"
EVALUATOR_SHA = "83e7954d0492418ea23cbbe585ee58665209e614d7553cc99e8b67e49be66903"


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["infer", "evaluate"])
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument(
        "--output", required=True, type=Path, help="Must not already exist."
    )
    parser.add_argument("--ocr-bundle", type=Path)
    parser.add_argument("--training-root", type=Path)
    parser.add_argument("--model-snapshot", type=Path)
    parser.add_argument("--base-reprovision", type=Path)
    parser.add_argument("--base-reprovision-sha256")
    parser.add_argument(
        "--methods", nargs="+", choices=["B0", "M0", "M1"], default=["B0", "M0", "M1"]
    )
    parser.add_argument(
        "--predictions-root",
        type=Path,
        help="Inference output directory for evaluation.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args(argv)
    repo = args.repo.resolve(strict=True)
    sys.path.insert(0, str(repo / "src"))
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        TOKENIZERS_PARALLELISM="false",
        VIETDOC_CONTRACTS_DIR=str(repo / "specs/contracts"),
        CUBLAS_WORKSPACE_CONFIG=":4096:8",
    )
    from vietdoc.ml.qwen_config import MLFailure

    from vietdoc.evaluation import extended
    from vietdoc.ml import dev_evaluation as ev

    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("timeout must be finite and positive")
    if len(args.methods) != len(set(args.methods)):
        parser.error("duplicate methods")
    manifest_path = args.snapshot_root.resolve(strict=True) / "manifest.json"
    manifest, dev = ev.select_dev(manifest_path, MANIFEST_SHA)
    if len(dev) != 16 or Counter(s["document_type"] for s in dev) != {
        "receipt": 8,
        "invoice": 8,
    }:
        raise MLFailure("D22_DEV_POPULATION_MISMATCH", "evaluation")
    if ev.evaluator_training_hash() != EVALUATOR_SHA:
        raise MLFailure("EVALUATOR_SOURCE_MISMATCH", "evaluation")
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {
        "context_id": CONTEXT_ID,
        "runner_sha256": ev.sha(Path(__file__)),
        "support_sha256": ev.sha(Path(ev.__file__)),
        "dataset_manifest_sha256": MANIFEST_SHA,
        "evaluator_sha256": EVALUATOR_SHA,
        "evaluator_source_hash": extended.source_hash(),
        "evaluator_version": extended.VERSION,
        "selected_ids": [s["sample_id"] for s in dev],
        "selected_count": len(dev),
        "production_active": False,
        "final_holdout_used": False,
    }
    identity["source_files"] = {
        rel: ev.sha(repo / rel)
        for rel in (
            "src/vietdoc/ml/dev_evaluation.py",
            "src/vietdoc/pipeline/extraction/baseline.py",
            "src/vietdoc/pipeline/extraction/table.py",
            "src/vietdoc/pipeline/extraction/output_parser.py",
            "src/vietdoc/pipeline/normalization.py",
            "src/vietdoc/contracts/compute.py",
            "src/vietdoc/data/generator/integration.py",
        )
    }
    ev.write_json(args.output / "identity.json", identity)
    try:
        if args.phase == "evaluate":
            if args.predictions_root is None:
                parser.error("--predictions-root required for evaluate")
            samples = ev.load_dev_gold(repo, manifest_path, manifest, dev)
            artifacts, diagnostics = {}, {}
            for method in args.methods:
                path = args.predictions_root / method / "predictions.json"
                artifacts[method], _, _ = ev._read_strict_json(
                    path, max_bytes=16 * 1024 * 1024
                )
                details, _, _ = ev._read_strict_json(
                    path.with_name("samples.json"), max_bytes=16 * 1024 * 1024
                )
                if details.get("predictions_sha256") != ev.sha(path):
                    raise MLFailure("DIAGNOSTIC_PREDICTION_MISMATCH", "evaluation")
                diagnostics[method] = details["samples"]
            result = ev.evaluate_artifacts(
                samples,
                artifacts,
                expected_manifest_sha256=MANIFEST_SHA,
                expected_ids=set(identity["selected_ids"]),
            )
            result["identity"] = identity
            result["raw_validity"] = {}
            for method, rows in diagnostics.items():
                # Count a missing/duplicate detail as invalid, never shrink denominator.
                by_id = {}
                for row in rows:
                    by_id.setdefault(row["sample_id"], []).append(row)
                result["raw_validity"][method] = {
                    key: {
                        "numerator": sum(
                            len(by_id.get(sid, [])) == 1
                            and by_id[sid][0].get(key) is True
                            for sid in identity["selected_ids"]
                        ),
                        "denominator": len(dev),
                    }
                    for key in (
                        "raw_json_valid",
                        "raw_schema_valid",
                        "normalized_schema_valid",
                    )
                }
                result["raw_validity"][method]["note"] = (
                    "B0 raw output is rules-produced JSON; token counts are null. "
                    "All methods scored through identical parser and evaluator normalizer."
                )
            ev.write_json(args.output / "comparison.json", result)
            for method, report in result["reports"].items():
                ev.write_json(args.output / (method + "-metrics.json"), report)
            return 0

        if args.training_root is None or args.ocr_bundle is None:
            parser.error("--training-root and --ocr-bundle required for infer")
        cfg, training = ev.verify_training_identity(
            args.training_root,
            repo,
            run_sha256=RUN_SHA,
            checkpoint_sha256=CHECKPOINT_SHA,
            config_sha256=CONFIG_SHA,
            preflight_sha256=PREFLIGHT_SHA,
        )
        pins = training["run"]["pins"]
        if (
            pins["dataset_manifest_sha256"] != MANIFEST_SHA
            or pins["evaluator_sha256"] != EVALUATOR_SHA
        ):
            raise MLFailure("TRAINING_PINS_MISMATCH", "evaluation")
        inputs, ocr_metadata = ev.inference_inputs(dev, args.ocr_bundle, pins)
        metadata = dict(
            identity,
            dataset_version=manifest["dataset_version"],
            schema_version="urn:vietdoc:business:v1",
            schema_sha256=cfg.schema_sha256,
            serialization_version=cfg.serialization_version,
            prompt_version=pins["prompt_version"],
            serialization_sha256=pins["serialization_sha256"],
            inference_config_sha256=cfg.config_sha256,
            **ocr_metadata,
        )
        metadata.update(
            adapter_run_sha256=RUN_SHA, adapter_checkpoint_sha256=CHECKPOINT_SHA
        )
        ev.write_json(
            args.output / "preflight.json",
            dict(
                metadata,
                training=training,
                budgets={
                    k: getattr(cfg, k)
                    for k in (
                        "max_ocr_tokens",
                        "max_input_tokens",
                        "max_new_tokens",
                        "max_sequence_tokens",
                    )
                },
            ),
        )
        runtime_versions = {}
        if set(args.methods) - {"B0"}:
            if args.model_snapshot is None:
                parser.error("--model-snapshot required for M0/M1")
            if sys.version_info[:2] != (3, 12):
                raise MLFailure("RUNTIME_VERSION_MISMATCH", "evaluation")
            for package, expected in [
                ("torch", "2.14.1+cu126"),
                ("transformers", "5.20.2"),
                ("peft", "0.21.2"),
            ]:
                runtime_versions[package] = importlib.metadata.version(package)
                if runtime_versions[package] != expected:
                    raise MLFailure("RUNTIME_VERSION_MISMATCH", "evaluation")
            base_identity = ev.verify_model_identity(args.model_snapshot, cfg, pins,
                reprovision=args.base_reprovision, reprovision_sha256=args.base_reprovision_sha256)
            ev.write_json(args.output / "base-identity.json", base_identity)
            import torch

            torch.manual_seed(training["run"]["seed"])
            torch.cuda.manual_seed_all(training["run"]["seed"])
            torch.use_deterministic_algorithms(True)
            ev.write_json(
                args.output / "environment.json",
                {
                    "python": platform.python_version(),
                    "versions": runtime_versions,
                    "cuda": torch.version.cuda,
                    "gpu": torch.cuda.get_device_name(cfg.device)
                    if torch.cuda.is_available()
                    else None,
                    "seed": training["run"]["seed"],
                    "decoding": {
                        "do_sample": False,
                        "num_beams": 1,
                        "max_new_tokens": cfg.max_new_tokens,
                        "enable_thinking": False,
                    },
                },
            )
        for method in ("B0", "M0", "M1"):
            if method not in args.methods:
                continue
            loader = None
            lifecycle_started = time.monotonic()
            load_seconds = None
            load_error = None
            gpu_peak = None
            try:
                if method != "B0":
                    torch.cuda.reset_peak_memory_stats(cfg.device)
                    from vietdoc.ml.model_loading import QwenLoader

                    loader = QwenLoader(
                        replace(cfg, execution_enabled=True), args.model_snapshot
                    )
                    loader.load()
                    if method == "M1":
                        # Recheck immediately before attachment; PEFT never resolves the archived base path.
                        ev.verify_training_identity(
                            args.training_root,
                            repo,
                            run_sha256=RUN_SHA,
                            checkpoint_sha256=CHECKPOINT_SHA,
                            config_sha256=CONFIG_SHA,
                            preflight_sha256=PREFLIGHT_SHA,
                        )
                        from peft import PeftModel

                        loader.model = PeftModel.from_pretrained(
                            loader.model,
                            str(
                                args.training_root
                                / "runs/full-epoch/checkpoint/adapter"
                            ),
                            is_trainable=False,
                            local_files_only=True,
                        )
                        loader.model.eval()
                        if any(p.requires_grad for p in loader.model.parameters()):
                            raise MLFailure("ADAPTER_TRAINABLE", "evaluation")
                        loader.provenance.update(
                            adapter_run_sha256=RUN_SHA,
                            adapter_checkpoint_sha256=CHECKPOINT_SHA,
                            peft_version=runtime_versions["peft"],
                        )
                    load_seconds = time.monotonic() - lifecycle_started
                ev.infer_method(
                    method,
                    dev,
                    inputs,
                    cfg,
                    metadata,
                    args.output / method,
                    loader=loader,
                    timeout_seconds=args.timeout_seconds,
                )
            except Exception as error:
                if (args.output / method).exists():
                    raise
                load_error = getattr(error, "code", type(error).__name__)
                load_seconds = time.monotonic() - lifecycle_started
                ev.infer_method(
                    method,
                    dev,
                    inputs,
                    cfg,
                    metadata,
                    args.output / method,
                    runtime_failure=load_error,
                )
            finally:
                cleanup_started = time.monotonic()
                if method != "B0" and torch.cuda.is_available():
                    gpu_peak = {
                        "max_memory_allocated_bytes": torch.cuda.max_memory_allocated(cfg.device),
                        "max_memory_reserved_bytes": torch.cuda.max_memory_reserved(cfg.device),
                    }
                if loader is not None:
                    ev.close_loader(loader)
                if (args.output / method).is_dir():
                    ev.write_json(
                        args.output / method / "lifecycle.json",
                        {
                            "load_seconds": load_seconds,
                            "load_error": load_error,
                            "gpu_peak": gpu_peak,
                            "cleanup_seconds": time.monotonic() - cleanup_started,
                            "method_seconds": time.monotonic() - lifecycle_started,
                            "model_closed_before_next_method": True,
                        },
                    )
        ev.write_json(
            args.output / "completed.json",
            dict(
                identity,
                methods=args.methods,
                status="INFERENCE_COMPLETED",
                promotion_eligible=False,
                note="Completion means all requested samples accounted for; inspect failed records and metrics.",
            ),
        )
        return 0
    except Exception as error:
        ev.write_json(
            args.output / "failure.json",
            dict(
                identity,
                status="FAILED",
                error=getattr(error, "code", type(error).__name__),
                stage=getattr(error, "stage", "runner"),
            ),
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
