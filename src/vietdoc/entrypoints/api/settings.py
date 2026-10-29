"""Runtime configuration for the private ai-service, read from the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from vietdoc.contracts.compute import default_contracts_dir

DEFAULT_MAX_INPUT_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    service_token: str
    models_dir: Path
    attempts_dir: Path
    contracts_dir: Path
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8090

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        token = env.get("VIETDOC_SERVICE_TOKEN", "")
        token_file = env.get("VIETDOC_SERVICE_TOKEN_FILE")
        if not token and token_file:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        contracts = env.get("VIETDOC_CONTRACTS_DIR")
        return cls(
            service_token=token,
            models_dir=Path(env.get("VIETDOC_MODELS_DIR", "artifacts/models")),
            attempts_dir=Path(env.get("VIETDOC_ATTEMPTS_DIR", "storage/attempts")),
            contracts_dir=Path(contracts) if contracts else default_contracts_dir(),
            max_input_bytes=int(env.get("VIETDOC_MAX_INPUT_BYTES", DEFAULT_MAX_INPUT_BYTES)),
            log_level=env.get("LOG_LEVEL", "INFO"),
            host=env.get("VIETDOC_HOST", "127.0.0.1"),
            port=int(env.get("VIETDOC_PORT", "8090")),
        )
