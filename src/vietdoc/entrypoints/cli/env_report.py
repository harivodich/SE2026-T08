"""Training/inference environment report for M1.1: `python -m vietdoc.entrypoints.cli.env_report`.

Prints measured facts only (interpreter, CPU, memory, package versions, torch
device support, verified releases); it does not download or load models.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from importlib import metadata
from pathlib import Path

from vietdoc.ml.release_manifest import discover_releases

PACKAGES = ("torch", "transformers", "peft", "accelerate", "safetensors", "pillow", "jsonschema", "fastapi")


def _memory_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def _torch() -> dict[str, object]:
    try:
        import torch
    except ImportError:
        return {"installed": False}
    info: dict[str, object] = {
        "installed": True,
        "build_cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "threads": torch.get_num_threads(),
    }
    if torch.cuda.is_available():
        info["devices"] = [
            {"name": torch.cuda.get_device_name(i), "memory_bytes": torch.cuda.get_device_properties(i).total_memory}
            for i in range(torch.cuda.device_count())
        ]
    return info


def report(models_dir: Path) -> dict[str, object]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    releases, errors = discover_releases(models_dir)
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
        "packages": versions,
        "torch": _torch(),
        "models_dir": str(models_dir),
        "releases": sorted(releases),
        "release_errors": errors,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, default=Path(os.environ.get("VIETDOC_MODELS_DIR", "artifacts/models")))
    args = parser.parse_args(argv)
    print(json.dumps(report(args.models_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
