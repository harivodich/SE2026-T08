"""Compute pipeline port used by the private ai-service (AI-2 wiring, AI-1 review).

Stages preprocess → OCR → extraction → normalization → evidence/confidence are not
implemented yet (O1.x, M2.1, M2.2). Until a pipeline is wired, the service starts
without one and reports NOT_READY / AI_NOT_READY instead of producing output.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from vietdoc.ml.release_manifest import Release


@dataclass(frozen=True)
class ComputeInput:
    request: Mapping[str, Any]
    document: bytes
    release: Release
    attempt_dir: Path
    deadline: float  # time.monotonic() value; stages must stop before it


class ComputePipeline(Protocol):
    def ready_reasons(self) -> list[str]:
        """Empty when models are loaded and a compute slot can run."""
        ...

    def run(self, job: ComputeInput) -> dict[str, Any]:
        """Blocking compute; returns a compute-response object for this attempt."""
        ...
