"""Explicit local candidate server. B0 is the default; never downloads weights."""
import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extractor", choices=("b0", "qwen-local"), default="b0")
    parser.add_argument("--ocr-artifact-version", type=int, choices=(1, 2), default=1)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-sha256")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--snapshot-manifest-sha256")
    parser.add_argument("--run-dir", type=Path, help="Optional verified LoRA run directory")
    parser.add_argument("--run-manifest-sha256")
    args = parser.parse_args(argv)
    if args.extractor == "qwen-local" and not all((args.config, args.config_sha256, args.snapshot,
                                                 args.snapshot_manifest_sha256)):
        parser.error("qwen-local needs explicit config/snapshot paths and SHA256 pins")
    if bool(args.run_dir) != bool(args.run_manifest_sha256):
        parser.error("--run-dir and --run-manifest-sha256 must be supplied together")
    if args.extractor == "b0" and any((args.config, args.snapshot, args.run_dir,
                                      args.config_sha256, args.snapshot_manifest_sha256,
                                      args.run_manifest_sha256)):
        parser.error("model options require --extractor qwen-local")
    import uvicorn

    from vietdoc.entrypoints.api.app import create_app
    from vietdoc.entrypoints.api.settings import Settings
    from vietdoc.pipeline.composition import ManagedPipeline
    from vietdoc.pipeline.extraction.baseline import BASELINE_VERSION
    from vietdoc.pipeline.normalization import POLICY_VERSION
    factory, version = None, BASELINE_VERSION
    normalizer = POLICY_VERSION
    if args.extractor == "qwen-local":
        from vietdoc.ml.compute_extractor import (
            NORMALIZER_VERSION,
            VERSION,
            QwenComputeExtractor,
        )
        version = VERSION
        normalizer = NORMALIZER_VERSION
        def factory(release):
            return QwenComputeExtractor(release, config=args.config, snapshot=args.snapshot,
                config_sha256=args.config_sha256,
                snapshot_manifest_sha256=args.snapshot_manifest_sha256,
                run_dir=args.run_dir, run_manifest_sha256=args.run_manifest_sha256)
    settings = Settings.from_env()
    pipeline = ManagedPipeline(settings.pipeline_manifest_id, extractor_factory=factory,
                               extractor_version=version, ocr_artifact_version=args.ocr_artifact_version,
                               normalizer_version=normalizer)
    uvicorn.run(create_app(settings, pipeline), host=settings.host, port=settings.port,
                workers=1, access_log=False, log_config=None, server_header=False)


if __name__ == "__main__":
    main()
