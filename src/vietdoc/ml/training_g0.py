"""Explicit opt-in offline G0 training-step, atomic checkpoint, and clean-process reload runner.

Preserves checked-in execution-disabled configs and B0 serving runtime.
No downloads, implicit GPU selection, automatic serving activation, or broad
filesystem output paths. Returns typed `TRAINING_DEPENDENCY_MISSING`/`G0_NOT_RUN`
when PyTorch is unavailable; never fabricates PASS.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import ctypes
from dataclasses import dataclass
import gc
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Literal, Protocol
import uuid

from vietdoc.data.adapters.labels import VERSION as LABEL_ADAPTER_VERSION
from vietdoc.ml import model_provision
from vietdoc.ml.ocr_adapter import PROMPT_VERSION
from vietdoc.ml.qwen_config import (
    MLFailure,
    QwenConfig,
    derive_inference_config_for_training,
    read_config_mapping,
)
from vietdoc.ml.training_dataset import (
    CollatedBatch,
    DataTrainingRecord,
    JoinedTrainingRecord,
    LABEL_IGNORE_INDEX,
    TrainingCollator,
    TrainingDataset,
    _canonical_json_bytes,
    _contained_file,
    _is_link,
    _is_nonblank_str,
    _is_sha256,
    _no_links,
    _read_strict_json,
    _safe_relative_posix,
    data_record_from_sample,
    join_training_dataset,
    load_ocr_handoff_bundle,
    token_preflight,
)

RUNNER_VERSION = "vietdoc.ai2-g0-training.v2"
CHECKPOINT_MANIFEST_VERSION = 1
RUN_MANIFEST_VERSION = 1
_DEVICE_RE = re.compile(r"^cpu|cuda:(?:0|[1-9][0-9]{0,5})$")
_RUN_DIR_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_VALID_DTYPES = frozenset(("float32", "float16", "bfloat16"))
_EVIDENCE_SCOPES = frozenset(("synthetic_machinery_only", "verified_model_run"))
_ALLOWED_ROOT_DIR_ITEMS = frozenset(("run_manifest.json", "checkpoint"))
_ADAPTER_CONFIG_REL = "adapter/adapter_config.json"
_ADAPTER_WEIGHTS_REL = "adapter/adapter_model.safetensors"
_SAFETENSORS_WIDTHS = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "I16": 2,
    "U16": 2,
    "F16": 2,
    "BF16": 2,
    "I32": 4,
    "U32": 4,
    "F32": 4,
    "I64": 8,
    "U64": 8,
    "F64": 8,
}
_MAX_SAFETENSORS_HEADER_BYTES = 16 * 1024 * 1024


class CollatorPort(Protocol):
    def collate(self, examples: Sequence[JoinedTrainingRecord]) -> CollatedBatch:
        ...


class TrainingModelPort(Protocol):
    def parameter_snapshot(self) -> Mapping[str, Sequence[float]]:
        ...

    def forward_loss(self, batch: CollatedBatch) -> Any:
        ...

    def loss_value(self, loss: Any) -> float:
        ...

    def backward(self, loss: Any) -> None:
        ...

    def gradient_snapshot(self) -> Mapping[str, Sequence[float]]:
        ...

    def clip_gradients(self, max_grad_norm: float) -> float:
        ...

    def zero_grad(self) -> None:
        ...

    def inference_probe(self, batch: CollatedBatch) -> Sequence[float]:
        ...

    def save_state(self, checkpoint_dir: Path) -> Sequence[str]:
        ...

    def load_state(self, checkpoint_dir: Path) -> None:
        ...


class OptimizerPort(Protocol):
    def step(self) -> None:
        ...

    def zero_grad(self) -> None:
        ...

    def save_state(self, checkpoint_dir: Path) -> Sequence[str]:
        ...


@dataclass(frozen=True)
class ArtifactPins:
    """Mandatory artifact hashes/versions; training fails closed if any pin is absent."""

    dataset_manifest_sha256: str | None
    sample_membership_sha256: str | None
    evaluator_version: str | None
    evaluator_sha256: str | None
    model_id: str | None
    model_revision: str | None
    model_manifest_sha256: str | None
    tokenizer_sha256: str | None
    schema_sha256: str | None
    ocr_engine_sha256: str | None
    ocr_profile_sha256: str | None
    serialization_version: str | None
    serialization_sha256: str | None
    prompt_version: str | None = PROMPT_VERSION
    label_adapter_version: str | None = LABEL_ADAPTER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "sample_membership_sha256": self.sample_membership_sha256,
            "evaluator_version": self.evaluator_version,
            "evaluator_sha256": self.evaluator_sha256,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "model_manifest_sha256": self.model_manifest_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "schema_sha256": self.schema_sha256,
            "ocr_engine_sha256": self.ocr_engine_sha256,
            "ocr_profile_sha256": self.ocr_profile_sha256,
            "serialization_version": self.serialization_version,
            "serialization_sha256": self.serialization_sha256,
            "prompt_version": self.prompt_version,
            "label_adapter_version": self.label_adapter_version,
        }


@dataclass(frozen=True)
class LoRAConfigSpec:
    """Validated adapter-only LoRA configuration matching `qwen-g0.yaml`."""

    method: str = "lora"
    task_type: str = "CAUSAL_LM"
    r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    bias: str = "none"
    target_modules: str = r".*model\.layers\.[0-9]+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)$"
    freeze_base_embeddings_and_lm_head: bool = True
    modules_to_save: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.method != "lora" or self.task_type != "CAUSAL_LM" or self.bias != "none":
            raise MLFailure("CONFIG_INVALID", "config")
        if type(self.r) is not int or not 1 <= self.r <= 128:
            raise MLFailure("CONFIG_INVALID", "config")
        if type(self.lora_alpha) is not int or not 1 <= self.lora_alpha <= 512:
            raise MLFailure("CONFIG_INVALID", "config")
        if (
            type(self.lora_dropout) not in (int, float)
            or not math.isfinite(self.lora_dropout)
            or not 0.0 <= self.lora_dropout < 1.0
        ):
            raise MLFailure("CONFIG_INVALID", "config")
        if not isinstance(self.target_modules, str) or not self.target_modules.strip():
            raise MLFailure("CONFIG_INVALID", "config")
        try:
            re.compile(self.target_modules)
        except re.error:
            raise MLFailure("CONFIG_INVALID", "config") from None
        if self.freeze_base_embeddings_and_lm_head is not True:
            raise MLFailure("CONFIG_INVALID", "config")
        if not isinstance(self.modules_to_save, tuple) or self.modules_to_save != ():
            raise MLFailure("CONFIG_INVALID", "config")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LoRAConfigSpec":
        if not isinstance(data, Mapping):
            raise MLFailure("CONFIG_INVALID", "config")
        try:
            raw_save = data.get("modules_to_save", [])
            if not isinstance(raw_save, (list, tuple)) or any(not isinstance(x, str) for x in raw_save):
                raise ValueError()
            spec = cls(
                method=data["method"],
                task_type=data["task_type"],
                r=data["r"],
                lora_alpha=data["lora_alpha"],
                lora_dropout=data["lora_dropout"],
                bias=data["bias"],
                target_modules=data["target_modules"],
                freeze_base_embeddings_and_lm_head=data["freeze_base_embeddings_and_lm_head"],
                modules_to_save=tuple(raw_save),
            )
            spec.validate()
            return spec
        except MLFailure:
            raise
        except (KeyError, TypeError, ValueError):
            raise MLFailure("CONFIG_INVALID", "config") from None


@dataclass(frozen=True)
class G0TrainingConfig:
    """Explicit opt-in G0 training settings; checked-in YAML keeps execution disabled."""

    execution_enabled: bool = False
    allow_training: bool = False
    allow_download: bool = False
    allow_paid_compute: bool = False
    runtime_activation: bool = False
    device: str = "cpu"
    dtype: str = "float32"
    seed: int = 2301
    micro_batch_size: int = 1
    gradient_accumulation_steps: int = 1
    max_optimizer_steps: int = 1
    require_full_epoch: bool = False
    max_grad_norm: float = 1.0
    min_parameter_delta: float = 0.0
    reload_tolerance: float = 1e-5
    label_ignore_index: int = LABEL_IGNORE_INDEX
    evidence_scope: Literal["synthetic_machinery_only", "verified_model_run"] = "synthetic_machinery_only"
    learning_rate: float = 1e-4
    weight_decay: float = 0.0
    gradient_checkpointing: bool = True
    use_cache: bool = False
    lora: LoRAConfigSpec = LoRAConfigSpec()
    inference_config: QwenConfig | None = None

    def validate(self) -> None:
        for flag in (
            self.execution_enabled,
            self.allow_training,
            self.allow_download,
            self.allow_paid_compute,
            self.runtime_activation,
            self.gradient_checkpointing,
            self.use_cache,
            self.require_full_epoch,
        ):
            if type(flag) is not bool:
                raise MLFailure("CONFIG_INVALID", "config")
        if self.allow_download or self.allow_paid_compute or self.runtime_activation or self.use_cache:
            raise MLFailure("CONFIG_INVALID", "config")
        if not isinstance(self.device, str) or not _DEVICE_RE.fullmatch(self.device):
            raise MLFailure("CONFIG_INVALID", "config")
        if self.dtype not in _VALID_DTYPES or (self.device == "cpu" and self.dtype != "float32"):
            raise MLFailure("CONFIG_INVALID", "config")
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise MLFailure("CONFIG_INVALID", "config")
        if (
            type(self.micro_batch_size) is not int
            or not 1 <= self.micro_batch_size <= 64
            or type(self.gradient_accumulation_steps) is not int
            or not 1 <= self.gradient_accumulation_steps <= 64
            or type(self.max_optimizer_steps) is not int
            or not 1 <= self.max_optimizer_steps <= 100
        ):
            raise MLFailure("CONFIG_INVALID", "config")
        if (
            type(self.max_grad_norm) not in (int, float)
            or not math.isfinite(self.max_grad_norm)
            or self.max_grad_norm <= 0
        ):
            raise MLFailure("CONFIG_INVALID", "config")
        if (
            type(self.learning_rate) not in (int, float)
            or not math.isfinite(self.learning_rate)
            or not 0.0 < self.learning_rate <= 0.1
        ):
            raise MLFailure("CONFIG_INVALID", "config")
        if (
            type(self.weight_decay) not in (int, float)
            or not math.isfinite(self.weight_decay)
            or not 0.0 <= self.weight_decay <= 1.0
        ):
            raise MLFailure("CONFIG_INVALID", "config")
        if (
            type(self.min_parameter_delta) not in (int, float)
            or not math.isfinite(self.min_parameter_delta)
            or self.min_parameter_delta < 0
        ):
            raise MLFailure("CONFIG_INVALID", "config")
        if (
            type(self.reload_tolerance) not in (int, float)
            or not math.isfinite(self.reload_tolerance)
            or self.reload_tolerance < 0
        ):
            raise MLFailure("CONFIG_INVALID", "config")
        if type(self.label_ignore_index) is not int or self.label_ignore_index != LABEL_IGNORE_INDEX:
            raise MLFailure("CONFIG_INVALID", "config")
        if self.evidence_scope not in _EVIDENCE_SCOPES:
            raise MLFailure("CONFIG_INVALID", "config")
        if not isinstance(self.lora, LoRAConfigSpec):
            raise MLFailure("CONFIG_INVALID", "config")
        self.lora.validate()
        if self.inference_config is not None:
            if not isinstance(self.inference_config, QwenConfig) or self.inference_config.execution_enabled is not False:
                raise MLFailure("CONFIG_INVALID", "config")

    def to_inference_config(self) -> QwenConfig:
        """Return the derived non-executable QwenConfig for dataset/collator parity."""
        if not isinstance(self.inference_config, QwenConfig) or self.inference_config.execution_enabled is not False:
            raise MLFailure("CONFIG_INVALID", "config")
        return self.inference_config

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], repository_root: Path) -> "G0TrainingConfig":
        """Parse a `qwen-g0.yaml`-compatible mapping while keeping forbidden modes closed."""
        try:
            if not isinstance(data, Mapping):
                raise ValueError()
            infer_cfg = derive_inference_config_for_training(data, repository_root)
            execution = data["execution"]
            g0 = data["training_g0"]
            if not isinstance(execution, Mapping) or not isinstance(g0, Mapping):
                raise ValueError()
            if (
                g0["input_profile"] != "ocr_text_layout_v1"
                or g0["observed_ocr_only"] is not True
                or g0["require_train_inference_serialization_parity"] is not True
                or g0["packing"] is not False
                or g0["truncation"] is not False
                or g0["independent_dev_and_final_access_in_g0"] is not False
            ):
                raise ValueError()
            if "max_sequence_tokens" in g0 and (
                type(g0["max_sequence_tokens"]) is not int
                or g0["max_sequence_tokens"] != infer_cfg.max_sequence_tokens
            ):
                raise ValueError()
            if "optimizer" in g0 and g0["optimizer"] != "adamw_torch":
                raise ValueError()
            lora_spec = LoRAConfigSpec.from_mapping(data["peft"]) if "peft" in data else LoRAConfigSpec()
            cfg = cls(
                execution_enabled=execution["enabled"],
                allow_training=execution.get("allow_training", False),
                allow_download=execution.get("allow_download", False),
                allow_paid_compute=execution.get("allow_paid_compute", False),
                runtime_activation=execution["runtime_activation"],
                device=infer_cfg.device,
                dtype=infer_cfg.dtype,
                seed=g0["seed"],
                micro_batch_size=g0["micro_batch_size"],
                gradient_accumulation_steps=g0["gradient_accumulation_steps"],
                max_optimizer_steps=g0["max_optimizer_steps"],
                require_full_epoch=g0.get("require_full_epoch", False),
                max_grad_norm=g0["max_grad_norm"],
                label_ignore_index=g0["label_ignore_index"],
                learning_rate=g0.get("learning_rate", 1e-4),
                weight_decay=g0.get("weight_decay", 0.0),
                gradient_checkpointing=g0.get("gradient_checkpointing", True),
                use_cache=g0.get("use_cache", False),
                lora=lora_spec,
                inference_config=infer_cfg,
            )
            cfg.validate()
            return cfg
        except MLFailure:
            raise
        except (KeyError, TypeError, ValueError, OSError):
            raise MLFailure("CONFIG_INVALID", "config") from None


def load_training_config(path: Path | str, repository_root: Path | None = None) -> G0TrainingConfig:
    """Load an explicit training YAML file while keeping inference `load_config` strict."""
    data, resolved_root = read_config_mapping(Path(path), repository_root)
    return G0TrainingConfig.from_mapping(data, resolved_root)


@dataclass(frozen=True)
class G0RunResult:
    """Typed outcome for offline G0 training runs; never fakes PASS."""

    status: Literal["G0_COMPLETED", "G0_NOT_RUN", "G0_FAILED"]
    error_code: str | None
    stage: str | None
    evidence_scope: str
    steps_completed: int = 0
    loss_history: tuple[float, ...] = ()
    max_grad_norm_observed: float | None = None
    parameter_delta_l2: float | None = None
    parameter_delta_max_abs: float | None = None
    output_dir: Path | None = None
    checkpoint_dir: Path | None = None
    run_manifest_path: Path | None = None
    checkpoint_manifest_sha256: str | None = None
    run_manifest_sha256: str | None = None
    reload_verified: bool = False
    reload_max_output_diff: float | None = None
    production_active: bool = False
    g0_acceptance_claimed: bool = False


def _import_torch():
    try:
        import torch
    except ImportError:
        raise MLFailure("TRAINING_DEPENDENCY_MISSING", "dependency") from None
    return torch


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _write_json_exclusive(path: Path, data: Any, *, stage: str = "checkpoint") -> tuple[bytes, str]:
    try:
        raw = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise MLFailure("JSON_INVALID", stage) from None
    _no_links(path.parent, stage=stage)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return raw, hashlib.sha256(raw).hexdigest()


def _tensor_float32_sha256(tensor: Any, torch_mod: Any) -> str:
    cpu_f32 = tensor.detach().to(device="cpu", dtype=torch_mod.float32).contiguous()
    if not bool(torch_mod.isfinite(cpu_f32).all().item()):
        raise MLFailure("NONFINITE_PARAMETER", "checkpoint")
    flat = cpu_f32.reshape(-1).tolist()
    packed = struct.pack(f"<{len(flat)}f", *flat) if flat else b""
    return hashlib.sha256(packed).hexdigest()


def _is_repo_root(path: Path) -> bool:
    return (path / "pyproject.toml").is_file() and (path / "specs" / "contracts").is_dir()


def validate_output_dir(allowed_output_root: Path | str, output_dir: Path | str) -> tuple[Path, Path]:
    """Enforce bounded, non-broad, symlink-free, non-existing output directory."""
    if not isinstance(allowed_output_root, (str, os.PathLike)) or not isinstance(output_dir, (str, os.PathLike)):
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    raw_root_str = os.fspath(allowed_output_root)
    raw_out_str = os.fspath(output_dir)
    if (
        not raw_root_str
        or not raw_out_str
        or any(ord(c) < 32 or ord(c) == 127 for c in raw_root_str)
        or any(ord(c) < 32 or ord(c) == 127 for c in raw_out_str)
    ):
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")

    root_path = Path(allowed_output_root)
    try:
        _no_links(root_path, stage="output")
    except MLFailure:
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output") from None
    try:
        resolved_root = root_path.resolve(strict=True)
    except OSError:
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output") from None
    if not resolved_root.is_dir():
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    if resolved_root.parent == resolved_root:
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    try:
        if resolved_root == Path.home().resolve():
            raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    except RuntimeError:
        pass
    if _is_repo_root(resolved_root):
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")

    out_path = Path(output_dir)
    if not out_path.is_absolute():
        if ".." in out_path.parts:
            raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
        out_path = resolved_root / out_path
    else:
        if ".." in out_path.parts:
            raise MLFailure("UNSAFE_OUTPUT_PATH", "output")

    try:
        _no_links(out_path, stage="output")
    except MLFailure:
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output") from None
    if _is_link(out_path):
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    # The allowed root itself is a broad container, never a run directory.  It
    # must be classified as unsafe even though it already exists; otherwise a
    # caller could confuse a policy violation with an ordinary idempotency hit.
    if out_path == resolved_root:
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    if out_path.exists():
        raise MLFailure("OUTPUT_EXISTS", "output")

    parent = out_path.parent
    try:
        _no_links(parent, stage="output")
    except MLFailure:
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output") from None
    try:
        resolved_parent = parent.resolve(strict=True)
    except OSError:
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output") from None
    if not resolved_parent.is_dir() or not resolved_parent.is_relative_to(resolved_root):
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    if not _RUN_DIR_NAME_RE.fullmatch(out_path.name):
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")

    resolved_out = resolved_parent / out_path.name
    if resolved_out == resolved_root or not resolved_out.is_relative_to(resolved_root):
        raise MLFailure("UNSAFE_OUTPUT_PATH", "output")
    if resolved_out.exists() or _is_link(resolved_out):
        raise MLFailure("OUTPUT_EXISTS", "output")
    return resolved_root, resolved_out


def validate_artifact_pins(
    pins: ArtifactPins,
    *,
    dataset: TrainingDataset | None = None,
    collated_serialization_sha256: str | None = None,
) -> None:
    """Fail closed if any required artifact pin is absent, malformed, or mismatched."""
    if not isinstance(pins, ArtifactPins):
        raise MLFailure("ARTIFACT_PINS_MISSING", "pins")

    required_hashes = (
        pins.dataset_manifest_sha256,
        pins.sample_membership_sha256,
        pins.evaluator_sha256,
        pins.model_manifest_sha256,
        pins.tokenizer_sha256,
        pins.schema_sha256,
        pins.ocr_engine_sha256,
        pins.ocr_profile_sha256,
        pins.serialization_sha256,
    )
    required_strings = (
        pins.evaluator_version,
        pins.model_id,
        pins.model_revision,
        pins.serialization_version,
        pins.prompt_version,
        pins.label_adapter_version,
    )
    if any(not _is_sha256(item) for item in required_hashes) or any(
        not _is_nonblank_str(item) for item in required_strings
    ):
        raise MLFailure("ARTIFACT_PINS_MISSING", "pins")

    if dataset is not None:
        if (
            pins.dataset_manifest_sha256 != dataset.source_manifest_sha256
            or pins.sample_membership_sha256 != dataset.sample_membership_sha256
            or pins.schema_sha256 != dataset.schema_sha256
            or pins.ocr_engine_sha256 != dataset.engine_sha256
            or pins.ocr_profile_sha256 != dataset.profile_sha256
            or pins.serialization_version != dataset.serialization_version
            or pins.prompt_version != dataset.prompt_version
            or pins.label_adapter_version != dataset.label_adapter_version
        ):
            raise MLFailure("ARTIFACT_PIN_MISMATCH", "pins")
        expected_ser = collated_serialization_sha256 or dataset.serialization_sha256
        if pins.serialization_sha256 not in (dataset.serialization_sha256, expected_ser):
            raise MLFailure("ARTIFACT_PIN_MISMATCH", "pins")


def _validate_finite_vector_map(
    vectors: Mapping[str, Sequence[float]],
    *,
    empty_code: str,
    nonfinite_code: str,
    stage: str,
) -> dict[str, tuple[float, ...]]:
    if not isinstance(vectors, Mapping) or not vectors:
        raise MLFailure(empty_code, stage)
    checked: dict[str, tuple[float, ...]] = {}
    total_elements = 0
    for name, values in vectors.items():
        if not isinstance(name, str) or not name or not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise MLFailure(nonfinite_code, stage)
        floats: list[float] = []
        for val in values:
            if type(val) not in (int, float):
                raise MLFailure(nonfinite_code, stage)
            fval = float(val)
            if not math.isfinite(fval):
                raise MLFailure(nonfinite_code, stage)
            floats.append(fval)
        total_elements += len(floats)
        checked[name] = tuple(floats)
    if total_elements == 0:
        raise MLFailure(empty_code, stage)
    return checked


def _parameter_delta(
    before: Mapping[str, tuple[float, ...]],
    after: Mapping[str, tuple[float, ...]],
) -> tuple[float, float]:
    if set(before) != set(after):
        raise MLFailure("PARAMETER_SET_CHANGED", "train_step")
    sq_sum = 0.0
    max_abs = 0.0
    for name, prev_vals in before.items():
        next_vals = after[name]
        if len(prev_vals) != len(next_vals):
            raise MLFailure("PARAMETER_SET_CHANGED", "train_step")
        for a, b in zip(prev_vals, next_vals):
            diff = abs(b - a)
            if not math.isfinite(diff):
                raise MLFailure("NONFINITE_PARAMETER", "train_step")
            if diff > max_abs:
                max_abs = diff
            sq_sum += diff * diff
    l2 = math.sqrt(sq_sum)
    if not math.isfinite(l2):
        raise MLFailure("NONFINITE_PARAMETER", "train_step")
    return l2, max_abs


def _validate_finite_sequence(values: Sequence[float], *, code: str, stage: str) -> list[float]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        raise MLFailure(code, stage)
    out: list[float] = []
    for val in values:
        if type(val) not in (int, float):
            raise MLFailure(code, stage)
        fval = float(val)
        if not math.isfinite(fval):
            raise MLFailure(code, stage)
        out.append(fval)
    return out


def _publish_dir_no_replace(source: Path, target: Path) -> str:
    """Publish staged directory atomically without replacing any existing destination."""
    if target.exists() or _is_link(target):
        raise MLFailure("OUTPUT_EXISTS", "checkpoint")
    if sys.platform == "win32":
        os.rename(source, target)
        return "atomic_directory_rename"
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) == 0:
            return "atomic_directory_rename"
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise MLFailure("OUTPUT_EXISTS", "checkpoint")
        if code not in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}:
            raise OSError(code, os.strerror(code))
    # Exclusive fallback copy writing run_manifest.json last.
    target.mkdir(exist_ok=False)
    ckpt_src = source / "checkpoint"
    ckpt_dst = target / "checkpoint"
    ckpt_dst.mkdir(exist_ok=False)
    for item in sorted(ckpt_src.rglob("*")):
        rel = item.relative_to(ckpt_src)
        dest = ckpt_dst / rel
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=False)
        elif item.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with item.open("rb") as src_stream, dest.open("xb") as dst_stream:
                shutil.copyfileobj(src_stream, dst_stream, 1024 * 1024)
                dst_stream.flush()
                os.fsync(dst_stream.fileno())
    with (source / "run_manifest.json").open("rb") as src_stream, (target / "run_manifest.json").open("xb") as dst_stream:
        shutil.copyfileobj(src_stream, dst_stream, 1024 * 1024)
        dst_stream.flush()
        os.fsync(dst_stream.fileno())
    shutil.rmtree(source, ignore_errors=True)
    return "exclusive_copy_manifest_last"


class TorchModelPort:
    """PyTorch adapter for a causal LM `torch.nn.Module`; uses `torch` lazily."""

    def __init__(
        self,
        model: Any,
        *,
        device: str = "cpu",
        loss_fn: Callable[[Any, Any, Any, Any], Any] | None = None,
        probe_fn: Callable[[Any, Any, Any], Any] | None = None,
        max_probe_values: int = 256,
    ) -> None:
        if not _DEVICE_RE.fullmatch(device):
            raise MLFailure("CONFIG_INVALID", "config")
        self.model = model
        self.device = device
        self._loss_fn = loss_fn
        self._probe_fn = probe_fn
        self._max_probe_values = max_probe_values

    def _torch(self):
        return _import_torch()

    def parameter_snapshot(self) -> dict[str, tuple[float, ...]]:
        torch = self._torch()
        snap: dict[str, tuple[float, ...]] = {}
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                cpu_vals = param.detach().to(device="cpu", dtype=torch.float32).contiguous().reshape(-1).tolist()
                snap[name] = tuple(float(v) for v in cpu_vals)
        return snap

    def forward_loss(self, batch: CollatedBatch) -> Any:
        torch = self._torch()
        self.model.train()
        input_ids = torch.tensor(batch.input_ids, dtype=torch.long, device=self.device)
        attention_mask = torch.tensor(batch.attention_mask, dtype=torch.long, device=self.device)
        labels = torch.tensor(batch.labels, dtype=torch.long, device=self.device)
        if self._loss_fn is not None:
            return self._loss_fn(self.model, input_ids, attention_mask, labels)
        out = self.model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        if hasattr(out, "loss") and out.loss is not None:
            return out.loss
        if isinstance(out, torch.Tensor) and out.ndim == 3:
            shift_logits = out[:, :-1, :].contiguous()
            shift_labels = labels[:, 1:].contiguous()
            return torch.nn.functional.cross_entropy(
                shift_logits.view(-1, shift_logits.size(-1)),
                shift_labels.view(-1),
                ignore_index=batch.label_ignore_index,
            )
        raise MLFailure("MODEL_OUTPUT_INVALID", "train_step")

    def loss_value(self, loss: Any) -> float:
        return float(loss.detach().cpu().item())

    def backward(self, loss: Any) -> None:
        loss.backward()

    def gradient_snapshot(self) -> dict[str, tuple[float, ...]]:
        torch = self._torch()
        grads: dict[str, tuple[float, ...]] = {}
        for name, param in self.model.named_parameters():
            if param.requires_grad and param.grad is not None:
                cpu_vals = param.grad.detach().to(device="cpu", dtype=torch.float32).contiguous().reshape(-1).tolist()
                grads[name] = tuple(float(v) for v in cpu_vals)
        return grads

    def clip_gradients(self, max_grad_norm: float) -> float:
        torch = self._torch()
        trainable = [p for p in self.model.parameters() if p.requires_grad and p.grad is not None]
        if not trainable:
            raise MLFailure("MISSING_GRADIENTS", "train_step")
        norm = torch.nn.utils.clip_grad_norm_(trainable, max_grad_norm)
        return float(norm.detach().cpu().item())

    def zero_grad(self) -> None:
        self.model.zero_grad(set_to_none=True)

    def inference_probe(self, batch: CollatedBatch) -> list[float]:
        torch = self._torch()
        self.model.eval()
        with torch.no_grad():
            input_ids = torch.tensor(batch.input_ids, dtype=torch.long, device=self.device)
            attention_mask = torch.tensor(batch.attention_mask, dtype=torch.long, device=self.device)
            if self._probe_fn is not None:
                out = self._probe_fn(self.model, input_ids, attention_mask)
            else:
                out = self.model(input_ids=input_ids, attention_mask=attention_mask)
                if hasattr(out, "logits"):
                    out = out.logits
            if not isinstance(out, torch.Tensor):
                raise MLFailure("MODEL_OUTPUT_INVALID", "reload")
            # Slice before CPU transfer/upcast: seq*vocab may be several GB.
            flat = out.detach().reshape(-1)[: self._max_probe_values]
            sliced = flat.to(device="cpu", dtype=torch.float32).contiguous().tolist()
            return [float(v) for v in sliced]

    def parameter_specs(self) -> dict[str, dict[str, Any]]:
        torch = self._torch()
        specs: dict[str, dict[str, Any]] = {}
        for name, tensor in self.model.state_dict().items():
            specs[name] = {
                "shape": list(tensor.shape),
                "dtype": str(tensor.dtype),
                "sha256": _tensor_float32_sha256(tensor, torch),
            }
        return specs

    def save_state(self, checkpoint_dir: Path) -> list[str]:
        torch = self._torch()
        _no_links(checkpoint_dir, stage="checkpoint")
        cpu_state = {name: tensor.detach().cpu().clone() for name, tensor in self.model.state_dict().items()}
        target = checkpoint_dir / "weights.pt"
        with target.open("xb") as stream:
            torch.save(cpu_state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        return ["weights.pt"]

    def load_state(self, checkpoint_dir: Path) -> None:
        torch = self._torch()
        target = _contained_file(checkpoint_dir, "weights.pt", stage="reload")
        state = torch.load(target, map_location="cpu", weights_only=True)
        if not isinstance(state, dict):
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device)


def validate_lora_target_modules(model: Any, lora: LoRAConfigSpec) -> tuple[str, ...]:
    """Ensure LoRA regex matches >=1 decoder attention modules and never embeddings/lm_head."""
    lora.validate()
    pattern = re.compile(lora.target_modules)
    named_modules = getattr(model, "named_modules", None)
    if not callable(named_modules):
        raise MLFailure("ADAPTER_TARGET_INVALID", "model")
    matched: list[str] = []
    for name, _module in named_modules():
        if not isinstance(name, str) or not name:
            continue
        if pattern.search(name):
            lowered = name.lower()
            if lora.freeze_base_embeddings_and_lm_head and ("embed" in lowered or "lm_head" in lowered):
                raise MLFailure("ADAPTER_TARGET_INVALID", "model")
            matched.append(name)
    if not matched:
        raise MLFailure("ADAPTER_TARGET_INVALID", "model")
    return tuple(sorted(matched))


def _verify_adapter_trainable_params(model: Any, lora: LoRAConfigSpec) -> tuple[str, ...]:
    named_params = getattr(model, "named_parameters", None)
    if not callable(named_params):
        raise MLFailure("NO_TRAINABLE_PARAMETERS", "model")
    trainable: list[str] = []
    for name, param in named_params():
        if not getattr(param, "requires_grad", False):
            continue
        lowered = name.lower()
        if "lora_" not in lowered:
            raise MLFailure("ADAPTER_TARGET_INVALID", "model")
        if lora.freeze_base_embeddings_and_lm_head and ("embed" in lowered or "lm_head" in lowered):
            raise MLFailure("ADAPTER_TARGET_INVALID", "model")
        trainable.append(name)
    if not trainable:
        raise MLFailure("NO_TRAINABLE_PARAMETERS", "model")
    return tuple(trainable)


def _is_forbidden_base_weight_rel(rel_path: str) -> bool:
    name = Path(rel_path).name
    if rel_path == "weights.pt" or name == "weights.pt":
        return True
    if name.endswith(".bin") and (name.startswith("pytorch_model") or name.startswith("model")):
        return True
    if name.endswith(".safetensors") and (
        name == "model.safetensors" or name.startswith("model-") or name == "model.safetensors.index.json"
    ):
        return True
    return False


def _verify_adapter_safetensors_file(
    path: Path,
    expected_specs: Mapping[str, Any] | None = None,
    *,
    verify_non_f32_with_torch: bool = False,
) -> tuple[int, int]:
    """Pure-Python adapter-only safetensors header/offset/name/F32-hash validator."""
    _no_links(path, stage="reload")
    try:
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            prefix = stream.read(8)
            if len(prefix) != 8:
                raise MLFailure("CORRUPT_CHECKPOINT", "reload")
            header_len = struct.unpack("<Q", prefix)[0]
            if not 0 < header_len <= _MAX_SAFETENSORS_HEADER_BYTES or header_len + 8 > file_size:
                raise MLFailure("CORRUPT_CHECKPOINT", "reload")
            raw_header = stream.read(header_len)
            payload_offset = 8 + header_len
            payload_size = file_size - payload_offset

            def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                out: dict[str, Any] = {}
                for k, v in pairs:
                    if k in out:
                        raise ValueError("duplicate key")
                    out[k] = v
                return out

            header = json.loads(
                raw_header.decode("utf-8", errors="strict"),
                object_pairs_hook=unique_pairs,
                parse_constant=lambda _v: (_ for _ in ()).throw(ValueError("nonfinite")),
            )
            if not isinstance(header, dict):
                raise MLFailure("CORRUPT_CHECKPOINT", "reload")

            tensors: dict[str, tuple[list[int], str, int, int]] = {}
            spans: list[tuple[int, int]] = []
            total_params = 0
            for key, value in header.items():
                if key == "__metadata__":
                    continue
                if not isinstance(key, str) or not isinstance(value, dict):
                    raise MLFailure("CORRUPT_CHECKPOINT", "reload")
                lowered = key.lower()
                if "lora_" not in lowered or "embed_tokens" in lowered or "lm_head" in lowered:
                    raise MLFailure("CORRUPT_CHECKPOINT", "reload")
                shape = value.get("shape")
                offsets = value.get("data_offsets")
                dtype = value.get("dtype")
                if (
                    not isinstance(shape, list)
                    or any(type(d) is not int or d < 0 for d in shape)
                    or not isinstance(offsets, list)
                    or len(offsets) != 2
                    or any(type(d) is not int or d < 0 for d in offsets)
                    or dtype not in _SAFETENSORS_WIDTHS
                ):
                    raise MLFailure("CORRUPT_CHECKPOINT", "reload")
                start, end = offsets
                numel = math.prod(shape) if shape else 1
                if end < start or end - start != numel * _SAFETENSORS_WIDTHS[dtype]:
                    raise MLFailure("CORRUPT_CHECKPOINT", "reload")
                tensors[key] = (shape, dtype, start, end)
                spans.append((start, end))
                total_params += numel

            if not tensors:
                raise MLFailure("CORRUPT_CHECKPOINT", "reload")
            cursor = 0
            for start, end in sorted(spans):
                if start != cursor:
                    raise MLFailure("CORRUPT_CHECKPOINT", "reload")
                cursor = end
            if cursor != payload_size:
                raise MLFailure("CORRUPT_CHECKPOINT", "reload")

            if expected_specs is not None:
                if not isinstance(expected_specs, Mapping) or set(tensors) != set(expected_specs):
                    raise MLFailure("CORRUPT_CHECKPOINT", "reload")
                need_torch_hashes: list[str] = []
                for name, (shape, dtype, start, end) in tensors.items():
                    spec = expected_specs[name]
                    if not isinstance(spec, Mapping) or shape != spec.get("shape"):
                        raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")
                    if dtype == "F32":
                        stream.seek(payload_offset + start)
                        raw_tensor = stream.read(end - start)
                        numel = (end - start) // 4
                        vals = struct.unpack(f"<{numel}f", raw_tensor) if numel else ()
                        if any(not math.isfinite(v) for v in vals):
                            raise MLFailure("NONFINITE_PARAMETER", "reload")
                        if hashlib.sha256(raw_tensor).hexdigest() != spec.get("sha256"):
                            raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")
                    else:
                        need_torch_hashes.append(name)

                if need_torch_hashes and verify_non_f32_with_torch:
                    try:
                        import safetensors.torch as st_torch
                        torch_mod = _import_torch()
                    except ImportError:
                        st_torch = None
                        torch_mod = None
                    if st_torch is not None and torch_mod is not None:
                        loaded = st_torch.load_file(str(path), device="cpu")
                        for name in need_torch_hashes:
                            if name not in loaded:
                                raise MLFailure("CORRUPT_CHECKPOINT", "reload")
                            if _tensor_float32_sha256(loaded[name], torch_mod) != expected_specs[name].get("sha256"):
                                raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")
            return len(tensors), total_params
    except MLFailure:
        raise
    except (OSError, ValueError, TypeError, struct.error):
        raise MLFailure("CORRUPT_CHECKPOINT", "reload") from None


class PeftLoraModelPort(TorchModelPort):
    """Adapter-only PEFT/LoRA port; saves/reloads ONLY adapter config and safetensors."""

    def __init__(
        self,
        model: Any,
        *,
        device: str = "cpu",
        peft_mod: Any,
        safetensors_torch_mod: Any,
        torch_mod: Any | None = None,
        loss_fn: Callable[[Any, Any, Any, Any], Any] | None = None,
        probe_fn: Callable[[Any, Any, Any], Any] | None = None,
        max_probe_values: int = 256,
        selective_logits: bool = False,
    ) -> None:
        super().__init__(
            model,
            device=device,
            loss_fn=loss_fn,
            probe_fn=probe_fn,
            max_probe_values=max_probe_values,
        )
        self._peft_mod = peft_mod
        self._safetensors_torch_mod = safetensors_torch_mod
        self._torch_mod = torch_mod
        self._selective_logits = selective_logits

    def _torch(self):
        return self._torch_mod if self._torch_mod is not None else _import_torch()

    def forward_loss(self, batch: CollatedBatch) -> Any:
        if not self._selective_logits:
            return super().forward_loss(batch)
        torch = self._torch()
        self.model.train()
        ids = torch.tensor(batch.input_ids, dtype=torch.long, device=self.device)
        mask = torch.tensor(batch.attention_mask, dtype=torch.long, device=self.device)
        labels = torch.tensor(batch.labels, dtype=torch.long, device=self.device)
        shifted = labels[:, 1:]
        # Causal position t predicts label t+1. Union supports right-padded
        # batches with different prompt lengths; ignored labels remain ignored.
        positions = torch.nonzero((shifted != batch.label_ignore_index).any(dim=0), as_tuple=False).flatten()
        if positions.numel() == 0:
            raise MLFailure("ASSISTANT_MASK_INVALID", "train_step")
        out = self.model(input_ids=ids, attention_mask=mask, use_cache=False,
                         logits_to_keep=positions)
        logits = out.logits
        targets = shifted.index_select(1, positions)
        return torch.nn.functional.cross_entropy(
            logits.float().reshape(-1, logits.size(-1)), targets.reshape(-1),
            ignore_index=batch.label_ignore_index)

    def inference_probe(self, batch: CollatedBatch) -> list[float]:
        if not self._selective_logits:
            return super().inference_probe(batch)
        torch = self._torch()
        self.model.eval()
        with torch.no_grad():
            # Same complete causal input, only its last-position logits. This
            # retains adapter-dependent output parity without seq*vocab output.
            ids = torch.tensor(batch.input_ids[:1], dtype=torch.long, device=self.device)
            mask = torch.tensor(batch.attention_mask[:1], dtype=torch.long, device=self.device)
            logits = self.model(input_ids=ids, attention_mask=mask, use_cache=False,
                                logits_to_keep=1).logits
            return logits.detach().reshape(-1)[:self._max_probe_values].float().cpu().tolist()

    def parameter_specs(self) -> dict[str, dict[str, Any]]:
        torch = self._torch()
        get_adapter_sd = getattr(self._peft_mod, "get_peft_model_state_dict", None)
        if callable(get_adapter_sd):
            adapter_state = get_adapter_sd(self.model)
        else:
            adapter_state = {
                name: param
                for name, param in self.model.named_parameters()
                if getattr(param, "requires_grad", False)
            }
        specs: dict[str, dict[str, Any]] = {}
        for name, tensor in adapter_state.items():
            specs[name] = {
                "shape": list(tensor.shape),
                "dtype": str(tensor.dtype),
                "sha256": _tensor_float32_sha256(tensor, torch),
            }
        return specs

    def save_state(self, checkpoint_dir: Path) -> list[str]:
        _no_links(checkpoint_dir, stage="checkpoint")
        adapter_dir = checkpoint_dir / "adapter"
        adapter_dir.mkdir(exist_ok=False)
        self.model.save_pretrained(str(adapter_dir), safe_serialization=True)

        saved: list[str] = []
        for item in sorted(adapter_dir.rglob("*")):
            if _is_link(item):
                raise MLFailure("UNSAFE_PATH", "checkpoint")
            if item.is_file():
                rel = item.relative_to(checkpoint_dir).as_posix()
                if _is_forbidden_base_weight_rel(rel):
                    raise MLFailure("ADAPTER_SAVE_NOT_ONLY", "checkpoint")
                saved.append(rel)
        if _ADAPTER_CONFIG_REL not in saved or _ADAPTER_WEIGHTS_REL not in saved:
            raise MLFailure("CHECKPOINT_WRITE_FAILED", "checkpoint")
        return sorted(saved)

    def load_state(self, checkpoint_dir: Path) -> None:
        _contained_file(checkpoint_dir, _ADAPTER_CONFIG_REL, stage="reload")
        weights_path = _contained_file(checkpoint_dir, _ADAPTER_WEIGHTS_REL, stage="reload")
        state = self._safetensors_torch_mod.load_file(str(weights_path), device="cpu")
        if not isinstance(state, dict) or not state:
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        set_adapter_sd = getattr(self._peft_mod, "set_peft_model_state_dict", None)
        if not callable(set_adapter_sd):
            raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload")
        set_adapter_sd(self.model, state)
        if callable(getattr(self.model, "to", None)):
            self.model.to(self.device)
        if callable(getattr(self.model, "eval", None)):
            self.model.eval()


class TorchOptimizerPort:
    """PyTorch optimizer port; persists JSON-safe hyperparameter/step summary."""

    def __init__(self, optimizer: Any) -> None:
        self.optimizer = optimizer
        self._steps = 0

    def step(self) -> None:
        self.optimizer.step()
        self._steps += 1

    def zero_grad(self) -> None:
        self.optimizer.zero_grad(set_to_none=True)

    def save_state(self, checkpoint_dir: Path) -> list[str]:
        groups = []
        for group in self.optimizer.param_groups:
            summary: dict[str, Any] = {}
            for key, value in group.items():
                if key == "params":
                    summary["param_count"] = len(value)
                elif isinstance(value, (int, float, bool, str)) or value is None:
                    summary[key] = value
                elif isinstance(value, (tuple, list)) and all(isinstance(v, (int, float, bool, str)) for v in value):
                    summary[key] = list(value)
            groups.append(summary)
        payload = {
            "optimizer_class": type(self.optimizer).__name__,
            "steps_completed": self._steps,
            "param_groups": groups,
        }
        _write_json_exclusive(checkpoint_dir / "optimizer_state.json", payload, stage="checkpoint")
        return ["optimizer_state.json"]


def verify_checkpoint(
    run_dir: Path | str,
    *,
    verify_torch_weights: bool = True,
) -> dict[str, Any]:
    """Strictly verify run_manifest.json, checkpoint_manifest.json, file hashes, and optional torch weights."""
    root = Path(run_dir)
    _no_links(root, stage="reload")
    if not root.is_dir():
        raise MLFailure("CHECKPOINT_MISSING", "reload")

    top_entries = {entry.name for entry in root.iterdir()}
    if top_entries != _ALLOWED_ROOT_DIR_ITEMS:
        raise MLFailure("CHECKPOINT_UNEXPECTED_FILES", "reload")

    run_manifest_path = _contained_file(root, "run_manifest.json", stage="reload")
    run_manifest, _, run_manifest_sha256 = _read_strict_json(run_manifest_path, stage="reload")
    if (
        not isinstance(run_manifest, dict)
        or run_manifest.get("manifest_version") != RUN_MANIFEST_VERSION
        or run_manifest.get("runner_version") != RUNNER_VERSION
        or run_manifest.get("production_active") is not False
        or run_manifest.get("serving_activated") is not False
        or run_manifest.get("g0_acceptance_claimed") is not False
    ):
        raise MLFailure("CORRUPT_CHECKPOINT", "reload")

    ckpt_ref = run_manifest.get("checkpoint")
    if (
        not isinstance(ckpt_ref, dict)
        or ckpt_ref.get("dir") != "checkpoint"
        or ckpt_ref.get("manifest_path") != "checkpoint/checkpoint_manifest.json"
        or not _is_sha256(ckpt_ref.get("manifest_sha256"))
    ):
        raise MLFailure("CORRUPT_CHECKPOINT", "reload")

    ckpt_dir = root / "checkpoint"
    _no_links(ckpt_dir, stage="reload")
    if not ckpt_dir.is_dir():
        raise MLFailure("CHECKPOINT_MISSING", "reload")

    ckpt_manifest_path = _contained_file(ckpt_dir, "checkpoint_manifest.json", stage="reload")
    ckpt_manifest, _, ckpt_manifest_sha256 = _read_strict_json(ckpt_manifest_path, stage="reload")
    if ckpt_manifest_sha256 != ckpt_ref["manifest_sha256"]:
        raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")

    if (
        not isinstance(ckpt_manifest, dict)
        or ckpt_manifest.get("manifest_version") != CHECKPOINT_MANIFEST_VERSION
        or ckpt_manifest.get("runner_version") != RUNNER_VERSION
        or ckpt_manifest.get("production_active") is not False
        or ckpt_manifest.get("serving_activated") is not False
        or ckpt_manifest.get("pins") != run_manifest.get("pins")
        or ckpt_manifest.get("seed") != run_manifest.get("seed")
        or ckpt_manifest.get("steps_completed") != run_manifest.get("steps_completed")
        or type(ckpt_manifest.get("seed")) is not int
        or type(ckpt_manifest.get("steps_completed")) is not int
        or ckpt_manifest["steps_completed"] < 1
    ):
        raise MLFailure("CORRUPT_CHECKPOINT", "reload")

    raw_pins = ckpt_manifest.get("pins")
    if not isinstance(raw_pins, dict):
        raise MLFailure("CORRUPT_CHECKPOINT", "reload")
    try:
        pins = ArtifactPins(**raw_pins)
    except TypeError:
        raise MLFailure("CORRUPT_CHECKPOINT", "reload") from None
    validate_artifact_pins(pins)

    files = ckpt_manifest.get("files")
    if not isinstance(files, list) or not files:
        raise MLFailure("CORRUPT_CHECKPOINT", "reload")

    declared_paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size_bytes"}:
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        rel_path, expected_sha, expected_size = entry["path"], entry["sha256"], entry["size_bytes"]
        _safe_relative_posix(rel_path, stage="reload")
        if (
            rel_path in declared_paths
            or rel_path == "checkpoint_manifest.json"
            or not _is_sha256(expected_sha)
            or type(expected_size) is not int
            or expected_size <= 0
        ):
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        declared_paths.add(rel_path)
        target = _contained_file(ckpt_dir, rel_path, stage="reload")
        actual_sha, actual_size = _sha256_file(target)
        if actual_size != expected_size or actual_sha != expected_sha:
            raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")

    actual_files: set[str] = set()
    for item in ckpt_dir.rglob("*"):
        if _is_link(item):
            raise MLFailure("UNSAFE_PATH", "reload")
        if item.is_file():
            actual_files.add(item.relative_to(ckpt_dir).as_posix())
    if actual_files != (declared_paths | {"checkpoint_manifest.json"}):
        raise MLFailure("CHECKPOINT_UNEXPECTED_FILES", "reload")

    if "probe_reference.json" not in declared_paths:
        raise MLFailure("CORRUPT_CHECKPOINT", "reload")
    probe_ref, _, _ = _read_strict_json(ckpt_dir / "probe_reference.json", stage="reload")
    if (
        not isinstance(probe_ref, dict)
        or not _is_sha256(probe_ref.get("probe_batch_sha256"))
        or "probe_output" not in probe_ref
    ):
        raise MLFailure("CORRUPT_CHECKPOINT", "reload")
    _validate_finite_sequence(probe_ref["probe_output"], code="CORRUPT_CHECKPOINT", stage="reload")

    torch_weights_verified = False
    adapter_only = False
    adapter_verified = False
    adapter_tensor_count = 0
    parameter_count = 0
    param_specs = ckpt_manifest.get("parameter_specs")

    has_adapter_files = any(rel.startswith("adapter/") for rel in declared_paths)
    if has_adapter_files:
        if _ADAPTER_CONFIG_REL not in declared_paths or _ADAPTER_WEIGHTS_REL not in declared_paths:
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        if any(_is_forbidden_base_weight_rel(rel) for rel in declared_paths):
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        adapter_cfg, _, _ = _read_strict_json(ckpt_dir / _ADAPTER_CONFIG_REL, stage="reload")
        if (
            not isinstance(adapter_cfg, dict)
            or adapter_cfg.get("peft_type") != "LORA"
            or adapter_cfg.get("task_type") != "CAUSAL_LM"
            or type(adapter_cfg.get("r")) is not int
            or adapter_cfg["r"] <= 0
        ):
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        adapter_tensor_count, parameter_count = _verify_adapter_safetensors_file(
            ckpt_dir / _ADAPTER_WEIGHTS_REL,
            expected_specs=param_specs if isinstance(param_specs, dict) else None,
            verify_non_f32_with_torch=verify_torch_weights,
        )
        adapter_only = True
        adapter_verified = True
    elif "weights.pt" in declared_paths and verify_torch_weights:
        if not isinstance(param_specs, dict) or not param_specs:
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        torch = _import_torch()
        try:
            state = torch.load(ckpt_dir / "weights.pt", map_location="cpu", weights_only=True)
        except Exception:
            raise MLFailure("CORRUPT_CHECKPOINT", "reload") from None
        if not isinstance(state, dict) or set(state) != set(param_specs):
            raise MLFailure("CORRUPT_CHECKPOINT", "reload")
        for name, spec in param_specs.items():
            tensor = state[name]
            if (
                not isinstance(spec, dict)
                or list(tensor.shape) != spec.get("shape")
                or str(tensor.dtype) != spec.get("dtype")
                or _tensor_float32_sha256(tensor, torch) != spec.get("sha256")
            ):
                raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")
            parameter_count += int(tensor.numel())
        torch_weights_verified = True

    return {
        "status": "verified",
        "checkpoint_manifest_sha256": ckpt_manifest_sha256,
        "run_manifest_sha256": run_manifest_sha256,
        "torch_weights_verified": torch_weights_verified,
        "adapter_only": adapter_only,
        "adapter_verified": adapter_verified,
        "adapter_tensor_count": adapter_tensor_count,
        "parameter_count": parameter_count,
        "steps_completed": ckpt_manifest["steps_completed"],
        "seed": ckpt_manifest["seed"],
        "production_active": False,
    }


def verify_checkpoint_in_clean_process(
    run_dir: Path | str,
    *,
    expected_checkpoint_manifest_sha256: str | None = None,
    expected_run_manifest_sha256: str | None = None,
    expect_torch_weights: bool = False,
    expect_adapter_only: bool = False,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Spawn a clean, offline Python process to independently verify and reload the checkpoint."""
    pkg_parent = str(Path(__file__).resolve().parents[2])
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "PYTEST_ADDOPTS")
    }
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{pkg_parent}{os.pathsep}{existing_pp}" if existing_pp else pkg_parent
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

    cmd = [sys.executable, "-B", "-m", "vietdoc.ml.training_g0", "--verify-checkpoint", str(Path(run_dir))]
    try:
        completed = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload") from None

    if completed.returncode != 0:
        raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload")
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload") from None

    if (
        not isinstance(payload, dict)
        or payload.get("status") != "verified"
        or payload.get("production_active") is not False
    ):
        raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload")
    if (
        expected_checkpoint_manifest_sha256 is not None
        and payload.get("checkpoint_manifest_sha256") != expected_checkpoint_manifest_sha256
    ):
        raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")
    if (
        expected_run_manifest_sha256 is not None
        and payload.get("run_manifest_sha256") != expected_run_manifest_sha256
    ):
        raise MLFailure("CHECKPOINT_HASH_MISMATCH", "reload")
    if expect_torch_weights and payload.get("torch_weights_verified") is not True:
        raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload")
    if expect_adapter_only and (
        payload.get("adapter_only") is not True or payload.get("adapter_verified") is not True
    ):
        raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload")
    return payload


def _verify_device_runtime(config: G0TrainingConfig, torch_mod: Any) -> None:
    if config.device.startswith("cuda:"):
        ordinal = int(config.device.split(":")[1])
        cuda = getattr(torch_mod, "cuda", None)
        if cuda is None or not cuda.is_available() or ordinal >= cuda.device_count():
            raise MLFailure("DEVICE_UNAVAILABLE", "dependency")
        if config.dtype == "bfloat16":
            with cuda.device(config.device):
                if not cuda.is_bf16_supported(including_emulation=False):
                    raise MLFailure("DTYPE_UNSUPPORTED", "dependency")


def _seed_runtime(seed: int, device: str, torch_mod: Any) -> None:
    random.seed(seed)
    manual_seed = getattr(torch_mod, "manual_seed", None)
    if callable(manual_seed):
        manual_seed(seed)
    if device.startswith("cuda:"):
        cuda = getattr(torch_mod, "cuda", None)
        if cuda is not None and callable(getattr(cuda, "manual_seed_all", None)):
            cuda.manual_seed_all(seed)


def _runtime_failure(error: BaseException, stage: str) -> MLFailure:
    oom = (isinstance(error, MemoryError) or type(error).__name__ in ('OutOfMemoryError', 'CudaOutOfMemoryError')
           or isinstance(error, RuntimeError) and 'out of memory' in str(error).lower())
    return MLFailure('OOM' if oom else 'TRAINING_RUNTIME_FAILED', stage)


def training_schedule(size: int, config: G0TrainingConfig) -> list[list[tuple[int, ...]]]:
    """Deterministic ordered microbatches; full epoch has no wrap or drop."""
    width = config.micro_batch_size * config.gradient_accumulation_steps
    required = math.ceil(size / width)
    if config.require_full_epoch and config.max_optimizer_steps < required:
        raise MLFailure('FULL_EPOCH_BUDGET_INSUFFICIENT', 'config')
    if config.require_full_epoch:
        batches = [tuple(range(start, min(size, start + config.micro_batch_size)))
                   for start in range(0, size, config.micro_batch_size)]
        return [batches[start:start + config.gradient_accumulation_steps]
                for start in range(0, len(batches), config.gradient_accumulation_steps)]
    return [[tuple((step * width + micro * config.micro_batch_size + offset) % size
                   for offset in range(config.micro_batch_size))
             for micro in range(config.gradient_accumulation_steps)]
            for step in range(config.max_optimizer_steps)]


def run_g0_training(
    *,
    config: G0TrainingConfig,
    pins: ArtifactPins,
    dataset: TrainingDataset,
    collator: CollatorPort,
    model_port: TrainingModelPort,
    optimizer_port: OptimizerPort,
    allowed_output_root: Path | str,
    output_dir: Path | str,
    fresh_model_factory: Callable[[], TrainingModelPort] | None = None,
    clean_process_verify: bool = True,
    clean_process_timeout_seconds: float = 30.0,
    torch_loader: Callable[[], Any] | None = None,
) -> G0RunResult:
    """Execute explicit opt-in G0 training steps, atomic checkpointing, and clean-process reload verification.

    Never fabricates PASS. Returns `G0_NOT_RUN` when execution is disabled, artifact
    pins are missing, or PyTorch is unavailable.
    """
    scope = config.evidence_scope if isinstance(config, G0TrainingConfig) else "synthetic_machinery_only"

    # 1. Config & explicit opt-in guard.
    try:
        if not isinstance(config, G0TrainingConfig):
            raise MLFailure("CONFIG_INVALID", "config")
        config.validate()
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    if not config.execution_enabled or not config.allow_training:
        return G0RunResult("G0_NOT_RUN", "TRAINING_EXECUTION_DISABLED", "config", scope)

    # 2. Dataset & mandatory artifact pins guard (fail closed when absent).
    if not isinstance(dataset, TrainingDataset) or not dataset.examples:
        return G0RunResult("G0_NOT_RUN", "NO_SUPERVISABLE_SAMPLES", "dataset", scope)
    try:
        validate_artifact_pins(pins, dataset=dataset)
        schedule = training_schedule(len(dataset.examples), config)
        if isinstance(collator, TrainingCollator):
            preflight = token_preflight(dataset, collator)
            if not preflight['ok']:
                first = next(row for row in preflight['rows'] if 'error_code' in row)
                raise MLFailure(first['error_code'], 'preflight')
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    # 3. Output path safety guard (before touching dependencies or files).
    try:
        _, resolved_output = validate_output_dir(allowed_output_root, output_dir)
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    # 4. Dependency & explicit device guard (never fake PASS when torch is absent).
    try:
        torch_mod = (torch_loader or _import_torch)()
        _verify_device_runtime(config, torch_mod)
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    _seed_runtime(config.seed, config.device, torch_mod)

    # 5. Deterministic probe batch & bounded training steps.
    steps_completed = 0
    loss_history: list[float] = []
    max_grad_norm_observed: float | None = None
    coverage = {example.sample_id: 0 for example in dataset.examples}
    current_stage = 'train_step'
    try:
        probe_batch = collator.collate(dataset.examples[: config.micro_batch_size])
        validate_artifact_pins(
            pins,
            dataset=dataset,
            collated_serialization_sha256=probe_batch.serialization_sha256,
        )
        initial_params = _validate_finite_vector_map(
            model_port.parameter_snapshot(),
            empty_code="NO_TRAINABLE_PARAMETERS",
            nonfinite_code="NONFINITE_PARAMETER",
            stage="train_step",
        )

        for group in schedule:
            optimizer_port.zero_grad()
            model_port.zero_grad()
            accumulated_losses: list[float] = []
            batches = [collator.collate([dataset.examples[i] for i in indices]) for indices in group]
            token_counts = [sum(token != config.label_ignore_index for row in b.labels for token in row[1:])
                            for b in batches]
            if any(count == 0 for count in token_counts):
                raise MLFailure('ASSISTANT_MASK_INVALID', 'train_step')
            total_tokens = sum(token_counts)
            for batch, token_count in zip(batches, token_counts):
                loss_obj = model_port.forward_loss(batch)
                loss_val = model_port.loss_value(loss_obj)
                if type(loss_val) not in (int, float) or not math.isfinite(loss_val):
                    raise MLFailure("NONFINITE_LOSS", "train_step")
                # Mean over supervised causal tokens across the whole update,
                # including a short final accumulation group. No prompt/pad loss.
                weight = token_count / total_tokens
                accumulated_losses.append(float(loss_val) * weight)
                model_port.backward(loss_obj if weight == 1 else loss_obj * weight)
                del loss_obj

            _validate_finite_vector_map(
                model_port.gradient_snapshot(),
                empty_code="MISSING_GRADIENTS",
                nonfinite_code="NONFINITE_GRADIENT",
                stage="train_step",
            )
            grad_norm = model_port.clip_gradients(config.max_grad_norm)
            if type(grad_norm) not in (int, float) or not math.isfinite(grad_norm) or grad_norm < 0:
                raise MLFailure("NONFINITE_GRADIENT", "train_step")
            max_grad_norm_observed = grad_norm if max_grad_norm_observed is None else max(max_grad_norm_observed, float(grad_norm))

            before_step = _validate_finite_vector_map(
                model_port.parameter_snapshot(),
                empty_code="NO_TRAINABLE_PARAMETERS",
                nonfinite_code="NONFINITE_PARAMETER",
                stage="train_step",
            )
            optimizer_port.step()
            after_step = _validate_finite_vector_map(
                model_port.parameter_snapshot(),
                empty_code="NO_TRAINABLE_PARAMETERS",
                nonfinite_code="NONFINITE_PARAMETER",
                stage="train_step",
            )
            _, step_max_abs = _parameter_delta(before_step, after_step)
            if step_max_abs <= config.min_parameter_delta:
                raise MLFailure("ZERO_PARAMETER_DELTA", "train_step")

            steps_completed += 1
            for batch in batches:
                for sid in batch.sample_ids:
                    coverage[sid] += 1
            loss_history.append(sum(accumulated_losses))

        final_params = _validate_finite_vector_map(
            model_port.parameter_snapshot(),
            empty_code="NO_TRAINABLE_PARAMETERS",
            nonfinite_code="NONFINITE_PARAMETER",
            stage="train_step",
        )
        total_delta_l2, total_delta_max_abs = _parameter_delta(initial_params, final_params)
        if total_delta_max_abs <= config.min_parameter_delta:
            raise MLFailure("ZERO_PARAMETER_DELTA", "train_step")

        if config.require_full_epoch and any(count != 1 for count in coverage.values()):
            raise MLFailure('FULL_EPOCH_COVERAGE_INVALID', 'train_step')
        optimizer_port.zero_grad()
        model_port.zero_grad()
        current_stage = 'reload'
        before_reload_probe = _validate_finite_sequence(
            model_port.inference_probe(probe_batch),
            code="MODEL_OUTPUT_INVALID",
            stage="reload",
        )
    except MLFailure as err:
        return G0RunResult(
            status="G0_FAILED",
            error_code=err.code,
            stage=err.stage,
            evidence_scope=scope,
            steps_completed=steps_completed,
            loss_history=tuple(loss_history),
            max_grad_norm_observed=max_grad_norm_observed,
        )

    except (RuntimeError, MemoryError) as error:
        err = _runtime_failure(error, current_stage)
        return G0RunResult('G0_FAILED', err.code, err.stage, scope,
                           steps_completed=steps_completed, loss_history=tuple(loss_history))

    # 6. Atomic staging, manifest hashing, and no-replace publication.
    stage_dir = resolved_output.parent / f".g0-stage-{resolved_output.name}-{uuid.uuid4().hex}"
    ckpt_manifest_sha256: str | None = None
    run_manifest_sha256: str | None = None
    expect_torch_weights = False
    expect_adapter_only = False
    try:
        stage_dir.mkdir(exist_ok=False)
        stage_ckpt = stage_dir / "checkpoint"
        stage_ckpt.mkdir(exist_ok=False)

        model_files = list(model_port.save_state(stage_ckpt))
        opt_files = list(optimizer_port.save_state(stage_ckpt))
        expect_torch_weights = "weights.pt" in model_files
        expect_adapter_only = _ADAPTER_WEIGHTS_REL in model_files

        probe_batch_sha256 = hashlib.sha256(
            _canonical_json_bytes(
                {
                    "sample_ids": list(probe_batch.sample_ids),
                    "input_ids": [list(row) for row in probe_batch.input_ids],
                    "attention_mask": [list(row) for row in probe_batch.attention_mask],
                },
                stage="checkpoint",
            )
        ).hexdigest()
        _write_json_exclusive(
            stage_ckpt / "probe_reference.json",
            {
                "probe_batch_sha256": probe_batch_sha256,
                "probe_output": before_reload_probe,
                "reload_tolerance": config.reload_tolerance,
            },
            stage="checkpoint",
        )

        saved_rel_paths = sorted(set(model_files) | set(opt_files) | {"probe_reference.json"})
        file_inventory: list[dict[str, Any]] = []
        for rel in saved_rel_paths:
            _safe_relative_posix(rel, stage="checkpoint")
            file_path = _contained_file(stage_ckpt, rel, stage="checkpoint")
            file_sha, file_size = _sha256_file(file_path)
            if file_size <= 0:
                raise MLFailure("CHECKPOINT_WRITE_FAILED", "checkpoint")
            file_inventory.append({"path": rel, "sha256": file_sha, "size_bytes": file_size})

        parameter_specs_fn = getattr(model_port, "parameter_specs", None)
        parameter_specs = parameter_specs_fn() if callable(parameter_specs_fn) else None

        checkpoint_manifest = {
            "manifest_version": CHECKPOINT_MANIFEST_VERSION,
            "runner_version": RUNNER_VERSION,
            "evidence_scope": scope,
            "production_active": False,
            "serving_activated": False,
            "seed": config.seed,
            "device": config.device,
            "dtype": config.dtype,
            "steps_completed": steps_completed,
            "loss_history": loss_history,
            "max_grad_norm_observed": max_grad_norm_observed,
            "parameter_delta": {"l2": total_delta_l2, "max_abs": total_delta_max_abs},
            "pins": pins.to_dict(),
            "collated_serialization_sha256": probe_batch.serialization_sha256,
            "parameter_specs": parameter_specs,
            "files": file_inventory,
        }
        _, ckpt_manifest_sha256 = _write_json_exclusive(
            stage_ckpt / "checkpoint_manifest.json",
            checkpoint_manifest,
            stage="checkpoint",
        )

        run_manifest = {
            "manifest_version": RUN_MANIFEST_VERSION,
            "runner_version": RUNNER_VERSION,
            "inference_config_sha256": config.inference_config.config_sha256 if config.inference_config else None,
            "evidence_scope": scope,
            "g0_acceptance_claimed": False,
            "production_active": False,
            "serving_activated": False,
            "seed": config.seed,
            "device": config.device,
            "dtype": config.dtype,
            "micro_batch_size": config.micro_batch_size,
            "gradient_accumulation_steps": config.gradient_accumulation_steps,
            "max_optimizer_steps": config.max_optimizer_steps,
            "max_grad_norm": config.max_grad_norm,
            "label_ignore_index": config.label_ignore_index,
            "steps_completed": steps_completed,
            "loss_history": loss_history,
            "max_grad_norm_observed": max_grad_norm_observed,
            "parameter_delta": {"l2": total_delta_l2, "max_abs": total_delta_max_abs},
            "pins": pins.to_dict(),
            "collated_serialization_sha256": probe_batch.serialization_sha256,
            "dataset_counts": dict(dataset.counts),
            "coverage": {"require_full_epoch": config.require_full_epoch,
                         "sample_visits": coverage, "examples_seen": sum(coverage.values()),
                         "unique_examples_seen": sum(n > 0 for n in coverage.values()),
                         "full_epochs_completed": min(coverage.values())},
            "label_status_totals": dict(dataset.status_totals),
            "excluded_samples": [
                {
                    "sample_id": item.sample_id,
                    "reason": item.reason,
                    "status_counts": dict(item.status_counts),
                    "obscured_pointers": list(item.obscured_pointers),
                    "unlabeled_pointers": list(item.unlabeled_pointers),
                }
                for item in dataset.excluded
            ],
            "checkpoint": {
                "dir": "checkpoint",
                "manifest_path": "checkpoint/checkpoint_manifest.json",
                "manifest_sha256": ckpt_manifest_sha256,
            },
        }
        _, run_manifest_sha256 = _write_json_exclusive(
            stage_dir / "run_manifest.json",
            run_manifest,
            stage="checkpoint",
        )

        # Verify staging integrity before publishing.
        verify_checkpoint(stage_dir, verify_torch_weights=expect_torch_weights)
        _publish_dir_no_replace(stage_dir, resolved_output)
    except MLFailure as err:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return G0RunResult(
            status="G0_FAILED",
            error_code=err.code,
            stage=err.stage,
            evidence_scope=scope,
            steps_completed=steps_completed,
            loss_history=tuple(loss_history),
            max_grad_norm_observed=max_grad_norm_observed,
            parameter_delta_l2=total_delta_l2,
            parameter_delta_max_abs=total_delta_max_abs,
        )
    except OSError:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return G0RunResult(
            status="G0_FAILED",
            error_code="CHECKPOINT_WRITE_FAILED",
            stage="checkpoint",
            evidence_scope=scope,
            steps_completed=steps_completed,
            loss_history=tuple(loss_history),
            max_grad_norm_observed=max_grad_norm_observed,
            parameter_delta_l2=total_delta_l2,
            parameter_delta_max_abs=total_delta_max_abs,
        )
    except (RuntimeError, MemoryError) as error:
        shutil.rmtree(stage_dir, ignore_errors=True)
        err = _runtime_failure(error, 'checkpoint')
        return G0RunResult('G0_FAILED', err.code, err.stage, scope, steps_completed=steps_completed)

    # 7. Clean-process reload verification & fresh-instance inference parity.
    reload_max_diff: float | None = None
    try:
        if clean_process_verify:
            verify_checkpoint_in_clean_process(
                resolved_output,
                expected_checkpoint_manifest_sha256=ckpt_manifest_sha256,
                expected_run_manifest_sha256=run_manifest_sha256,
                expect_torch_weights=expect_torch_weights,
                expect_adapter_only=expect_adapter_only,
                timeout_seconds=clean_process_timeout_seconds,
            )
        else:
            verify_checkpoint(resolved_output, verify_torch_weights=expect_torch_weights)

        if fresh_model_factory is not None:
            reloaded_port = fresh_model_factory()
            reloaded_port.load_state(resolved_output / "checkpoint")
            if expect_adapter_only and reloaded_port.parameter_specs() != parameter_specs:
                raise MLFailure('RELOAD_VERIFICATION_FAILED', 'reload')
            after_reload_probe = _validate_finite_sequence(
                reloaded_port.inference_probe(probe_batch),
                code="RELOAD_VERIFICATION_FAILED",
                stage="reload",
            )
            if len(after_reload_probe) != len(before_reload_probe):
                raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload")
            reload_max_diff = max(abs(a - b) for a, b in zip(before_reload_probe, after_reload_probe))
            if not math.isfinite(reload_max_diff) or reload_max_diff > config.reload_tolerance:
                raise MLFailure("RELOAD_VERIFICATION_FAILED", "reload")
    except MLFailure as err:
        return G0RunResult(
            status="G0_FAILED",
            error_code=err.code,
            stage=err.stage,
            evidence_scope=scope,
            steps_completed=steps_completed,
            loss_history=tuple(loss_history),
            max_grad_norm_observed=max_grad_norm_observed,
            parameter_delta_l2=total_delta_l2,
            parameter_delta_max_abs=total_delta_max_abs,
            output_dir=resolved_output,
            checkpoint_dir=resolved_output / "checkpoint",
            run_manifest_path=resolved_output / "run_manifest.json",
            checkpoint_manifest_sha256=ckpt_manifest_sha256,
            run_manifest_sha256=run_manifest_sha256,
            reload_verified=False,
            reload_max_output_diff=reload_max_diff,
        )

    except (RuntimeError, MemoryError) as error:
        err = _runtime_failure(error, 'reload')
        return G0RunResult('G0_FAILED', err.code, err.stage, scope,
                           steps_completed=steps_completed, output_dir=resolved_output)

    return G0RunResult(
        status="G0_COMPLETED",
        error_code=None,
        stage=None,
        evidence_scope=scope,
        steps_completed=steps_completed,
        loss_history=tuple(loss_history),
        max_grad_norm_observed=max_grad_norm_observed,
        parameter_delta_l2=total_delta_l2,
        parameter_delta_max_abs=total_delta_max_abs,
        output_dir=resolved_output,
        checkpoint_dir=resolved_output / "checkpoint",
        run_manifest_path=resolved_output / "run_manifest.json",
        checkpoint_manifest_sha256=ckpt_manifest_sha256,
        run_manifest_sha256=run_manifest_sha256,
        reload_verified=True,
        reload_max_output_diff=reload_max_diff,
        production_active=False,
        g0_acceptance_claimed=False,
    )


def _load_peft_training_runtime() -> Any:
    """Lazily import offline training dependencies; never install or download."""
    try:
        import peft
        import safetensors.torch as safetensors_torch
        import torch
        import transformers
    except ImportError:
        raise MLFailure("TRAINING_DEPENDENCY_MISSING", "dependency") from None
    return SimpleNamespace(
        torch=torch,
        transformers=transformers,
        peft=peft,
        safetensors_torch=safetensors_torch,
        tokenizer_cls=transformers.AutoTokenizer,
        model_cls=transformers.AutoModelForCausalLM,
        selective_logits=True,
    )


def _load_data_records_file(
    records_path: Path,
) -> tuple[list[DataTrainingRecord], list[DataTrainingRecord], str | None]:
    """Read a `vietdoc.training-records.v1` or `vietdoc.pilot-records-preparation.v1` file."""
    raw, _, _ = _read_strict_json(records_path, stage="dataset", max_bytes=32 * 1024 * 1024)
    if not isinstance(raw, dict):
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    version = raw.get("artifact_version")
    if version == "vietdoc.pilot-records-preparation.v1":
        packet = raw.get("training_records")
    elif version == "vietdoc.training-records.v1":
        packet = raw
    else:
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    if not isinstance(packet, dict) or packet.get("artifact_version") != "vietdoc.training-records.v1":
        raise MLFailure("DATA_RECORD_INVALID", "dataset")
    manifest_info = packet.get("manifest")
    manifest_sha = manifest_info.get("sha256") if isinstance(manifest_info, dict) else None
    if manifest_sha is not None and not _is_sha256(manifest_sha):
        raise MLFailure("PROVENANCE_MISMATCH", "dataset")
    entries = packet.get("records")
    if not isinstance(entries, list) or not entries:
        raise MLFailure("DATA_RECORDS_EMPTY", "dataset")

    train_records: list[DataTrainingRecord] = []
    dev_records: list[DataTrainingRecord] = []
    for entry in entries:
        if not isinstance(entry, dict) or not {"sample", "gold", "labels"} <= set(entry):
            raise MLFailure("DATA_RECORD_INVALID", "dataset")
        rec = data_record_from_sample(
            entry["sample"],
            entry["gold"],
            entry["labels"],
            dataset_manifest_sha256=manifest_sha,
        )
        if rec.split == "final":
            raise MLFailure("FINAL_SPLIT_FORBIDDEN", "dataset")
        if rec.split == "train":
            train_records.append(rec)
        elif rec.split == "dev":
            dev_records.append(rec)
        else:
            raise MLFailure("SPLIT_INVALID", "dataset")
    if not train_records:
        raise MLFailure("DATA_RECORDS_EMPTY", "dataset")
    return train_records, dev_records, manifest_sha


def _build_peft_lora_model(
    runtime: Any,
    snapshot: Path,
    infer_cfg: QwenConfig,
    train_cfg: G0TrainingConfig,
) -> Any:
    torch_mod = runtime.torch
    torch_dtype = getattr(torch_mod, train_cfg.dtype, None)
    if torch_dtype is None:
        raise MLFailure("DTYPE_UNSUPPORTED", "dependency")
    base_model = runtime.model_cls.from_pretrained(
        str(snapshot),
        local_files_only=True,
        trust_remote_code=False,
        revision=infer_cfg.revision,
        use_safetensors=True,
        torch_dtype=torch_dtype,
        attn_implementation="sdpa",
    )
    if getattr(base_model, "config", None) is not None:
        base_model.config.use_cache = False
    if train_cfg.gradient_checkpointing and callable(getattr(base_model, "gradient_checkpointing_enable", None)):
        base_model.gradient_checkpointing_enable()
    validate_lora_target_modules(base_model, train_cfg.lora)
    for _name, param in base_model.named_parameters():
        param.requires_grad = False
    lora_cfg = runtime.peft.LoraConfig(
        task_type=train_cfg.lora.task_type,
        r=train_cfg.lora.r,
        lora_alpha=train_cfg.lora.lora_alpha,
        lora_dropout=train_cfg.lora.lora_dropout,
        bias=train_cfg.lora.bias,
        target_modules=train_cfg.lora.target_modules,
        modules_to_save=list(train_cfg.lora.modules_to_save) if train_cfg.lora.modules_to_save else None,
    )
    peft_model = runtime.peft.get_peft_model(base_model, lora_cfg)
    _verify_adapter_trainable_params(peft_model, train_cfg.lora)
    if callable(getattr(peft_model, "to", None)):
        try:
            peft_model.to(train_cfg.device)
        except (RuntimeError, MemoryError):
            # A failed transfer can leave a partially placed model alive in
            # the exception traceback. Release its CUDA tensors before return.
            peft_model.to('cpu')
            gc.collect()
            if train_cfg.device.startswith('cuda:'):
                torch_mod.cuda.empty_cache()
            raise
    return peft_model


def run_qwen_lora_g0_training(
    *,
    snapshot_dir: Path | str,
    ocr_bundle_dir: Path | str,
    records_path: Path | str,
    allowed_output_root: Path | str,
    output_dir: Path | str,
    evaluator_version: str | None,
    evaluator_sha256: str | None,
    config_path: Path | str | None = None,
    config: G0TrainingConfig | None = None,
    repository_root: Path | None = None,
    expected_engine_sha256: str | None = None,
    expected_profile_sha256: str | None = None,
    clean_process_verify: bool = True,
    clean_process_timeout_seconds: float = 60.0,
    runtime_factory: Callable[[], Any] | None = None,
    snapshot_verifier: Callable[[Path], Mapping[str, Any]] | None = None,
    evidence_scope: Literal["synthetic_machinery_only", "verified_model_run"] = "verified_model_run",
) -> G0RunResult:
    """Bounded opt-in PEFT/LoRA G0 entrypoint with adapter-only checkpoint & reload verification.

    Never downloads weights, never activates serving, never weakens checked-in
    disabled config guards, and returns typed `G0_NOT_RUN` when disabled, pins
    are missing, or training runtime dependencies are absent.
    """
    scope = evidence_scope if evidence_scope in _EVIDENCE_SCOPES else "verified_model_run"

    # 1. Load & validate explicit training config before touching snapshots or frameworks.
    try:
        if (config_path is None) == (config is None):
            raise MLFailure("CONFIG_INVALID", "config")
        train_cfg = (
            load_training_config(config_path, repository_root=repository_root)
            if config_path is not None
            else config
        )
        if not isinstance(train_cfg, G0TrainingConfig):
            raise MLFailure("CONFIG_INVALID", "config")
        train_cfg.validate()
        infer_cfg = train_cfg.to_inference_config()
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    if not train_cfg.execution_enabled or not train_cfg.allow_training:
        return G0RunResult("G0_NOT_RUN", "TRAINING_EXECUTION_DISABLED", "config", scope)

    # 2. Output path and mandatory caller pin checks before model/data loading.
    try:
        validate_output_dir(allowed_output_root, output_dir)
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    if not _is_nonblank_str(evaluator_version) or not _is_sha256(evaluator_sha256):
        return G0RunResult("G0_NOT_RUN", "ARTIFACT_PINS_MISSING", "pins", scope)

    # 3. Verify local pretrained model snapshot offline.
    snapshot = Path(snapshot_dir).absolute()
    try:
        verifier = snapshot_verifier or model_provision.verify_snapshot
        verified = verifier(snapshot)
        if (
            not isinstance(verified, Mapping)
            or verified.get("model_id") != infer_cfg.model_id
            or verified.get("revision") != infer_cfg.revision
        ):
            raise ValueError()
        model_manifest_sha256, _ = _sha256_file(_contained_file(snapshot, "manifest.json", stage="model"))
        tokenizer_sha256, _ = _sha256_file(_contained_file(snapshot, "tokenizer.json", stage="model"))
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)
    except Exception:
        return G0RunResult("G0_NOT_RUN", "MODEL_NOT_VERIFIED", "model", scope)

    # 4. Verify OCR handoff bundle & Data training records join (train split only, dev as leak check).
    try:
        handoff_index = load_ocr_handoff_bundle(
            ocr_bundle_dir,
            expected_engine_sha256=expected_engine_sha256,
            expected_profile_sha256=expected_profile_sha256,
        )
        train_records, dev_records, manifest_sha = _load_data_records_file(Path(records_path))
        dataset = join_training_dataset(
            handoff_index,
            train_records,
            infer_cfg,
            expected_engine_sha256=expected_engine_sha256 or handoff_index.engine_sha256,
            expected_profile_sha256=expected_profile_sha256 or handoff_index.profile_sha256,
            target_split="train",
            expected_dataset_manifest_sha256=manifest_sha,
            reference_records=dev_records or None,
        )
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    if not dataset.examples:
        return G0RunResult("G0_NOT_RUN", "NO_SUPERVISABLE_SAMPLES", "dataset", scope)

    # 5. Lazily load training dependencies & check explicit device/dtype support.
    try:
        runtime = (runtime_factory or _load_peft_training_runtime)()
        _verify_device_runtime(train_cfg, runtime.torch)
    except MLFailure as err:
        return G0RunResult("G0_NOT_RUN", err.code, err.stage, scope)

    # 6. Load local tokenizer, build PEFT/LoRA model + AdamW optimizer on trainable LoRA params only.
    try:
        tokenizer = runtime.tokenizer_cls.from_pretrained(
            str(snapshot),
            local_files_only=True,
            trust_remote_code=False,
            revision=infer_cfg.revision,
        )
        collator = TrainingCollator(infer_cfg, tokenizer, label_ignore_index=train_cfg.label_ignore_index)
        preflight = token_preflight(dataset, collator)
        if not preflight['ok']:
            first = next(row for row in preflight['rows'] if 'error_code' in row)
            raise MLFailure(first['error_code'], 'preflight')
        training_schedule(len(dataset.examples), train_cfg)
        _seed_runtime(train_cfg.seed, train_cfg.device, runtime.torch)
        pins = ArtifactPins(
            dataset_manifest_sha256=dataset.source_manifest_sha256,
            sample_membership_sha256=dataset.sample_membership_sha256,
            evaluator_version=evaluator_version,
            evaluator_sha256=evaluator_sha256,
            model_id=infer_cfg.model_id,
            model_revision=infer_cfg.revision,
            model_manifest_sha256=model_manifest_sha256,
            tokenizer_sha256=tokenizer_sha256,
            schema_sha256=dataset.schema_sha256,
            ocr_engine_sha256=dataset.engine_sha256,
            ocr_profile_sha256=dataset.profile_sha256,
            serialization_version=dataset.serialization_version,
            serialization_sha256=dataset.serialization_sha256,
            prompt_version=dataset.prompt_version,
            label_adapter_version=dataset.label_adapter_version,
        )
        peft_model = _build_peft_lora_model(runtime, snapshot, infer_cfg, train_cfg)
        trainable_params = [p for p in peft_model.parameters() if getattr(p, "requires_grad", False)]
        if not trainable_params:
            raise MLFailure("NO_TRAINABLE_PARAMETERS", "model")
        optimizer = runtime.torch.optim.AdamW(
            trainable_params,
            lr=train_cfg.learning_rate,
            weight_decay=train_cfg.weight_decay,
        )
        model_port = PeftLoraModelPort(
            peft_model,
            device=train_cfg.device,
            peft_mod=runtime.peft,
            safetensors_torch_mod=runtime.safetensors_torch,
            torch_mod=runtime.torch,
            selective_logits=getattr(runtime, 'selective_logits', False),
        )
        optimizer_port = TorchOptimizerPort(optimizer)
    except MLFailure as err:
        return G0RunResult("G0_FAILED", err.code, err.stage, scope)
    except (RuntimeError, MemoryError) as error:
        err = _runtime_failure(error, 'model')
        return G0RunResult('G0_FAILED', err.code, err.stage, scope)
    except Exception:
        return G0RunResult("G0_FAILED", "MODEL_LOAD_FAILED", "model", scope)

    fresh_ports = []
    def fresh_model_factory() -> PeftLoraModelPort:
        # On 12GB GPUs (e.g., RTX 3060), offload trained model before loading fresh reload instance.
        if train_cfg.device.startswith("cuda:") and callable(getattr(peft_model, "to", None)):
            optimizer.zero_grad(set_to_none=True)
            optimizer.state.clear()
            peft_model.to("cpu")
            gc.collect()
            runtime.torch.cuda.empty_cache()
        fresh_peft = _build_peft_lora_model(runtime, snapshot, infer_cfg, train_cfg)
        port = PeftLoraModelPort(
            fresh_peft,
            device=train_cfg.device,
            peft_mod=runtime.peft,
            safetensors_torch_mod=runtime.safetensors_torch,
            torch_mod=runtime.torch,
            selective_logits=getattr(runtime, 'selective_logits', False),
        )
        fresh_ports.append(port)
        return port

    effective_cfg = G0TrainingConfig(
        execution_enabled=train_cfg.execution_enabled,
        allow_training=train_cfg.allow_training,
        allow_download=train_cfg.allow_download,
        allow_paid_compute=train_cfg.allow_paid_compute,
        runtime_activation=train_cfg.runtime_activation,
        device=train_cfg.device,
        dtype=train_cfg.dtype,
        seed=train_cfg.seed,
        micro_batch_size=train_cfg.micro_batch_size,
        gradient_accumulation_steps=train_cfg.gradient_accumulation_steps,
        max_optimizer_steps=train_cfg.max_optimizer_steps,
        require_full_epoch=train_cfg.require_full_epoch,
        max_grad_norm=train_cfg.max_grad_norm,
        min_parameter_delta=train_cfg.min_parameter_delta,
        reload_tolerance=train_cfg.reload_tolerance,
        label_ignore_index=train_cfg.label_ignore_index,
        evidence_scope=scope,
        learning_rate=train_cfg.learning_rate,
        weight_decay=train_cfg.weight_decay,
        gradient_checkpointing=train_cfg.gradient_checkpointing,
        use_cache=train_cfg.use_cache,
        lora=train_cfg.lora,
        inference_config=infer_cfg,
    )
    try:
        return run_g0_training(
            config=effective_cfg,
            pins=pins,
            dataset=dataset,
            collator=collator,
            model_port=model_port,
            optimizer_port=optimizer_port,
            allowed_output_root=allowed_output_root,
            output_dir=output_dir,
            fresh_model_factory=fresh_model_factory,
            clean_process_verify=clean_process_verify,
            clean_process_timeout_seconds=clean_process_timeout_seconds,
            torch_loader=lambda: runtime.torch,
        )
    finally:
        # Release gradients and optimizer buffers even on OOM/failed reload.
        optimizer_port.zero_grad()
        state = getattr(optimizer, 'state', None)
        if state is not None:
            state.clear()
        for port in [model_port, *fresh_ports]:
            port.zero_grad()
            port.model.to('cpu')
        fresh_ports.clear()
        gc.collect()
        if train_cfg.device.startswith('cuda:'):
            runtime.torch.cuda.empty_cache()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--verify-checkpoint",
        type=Path,
        help="Offline, read-only verification of a G0 run/checkpoint directory in a clean process.",
    )
    mode.add_argument(
        "--train",
        action="store_true",
        help="Explicit opt-in bounded offline PEFT/LoRA G0 training run (never enables serving).",
    )
    parser.add_argument("--config", type=Path, help="Local training YAML config (opt-in copy).")
    parser.add_argument("--snapshot", type=Path, help="Verified local Qwen snapshot directory.")
    parser.add_argument("--ocr-bundle", type=Path, help="Verified AI-2 OCR handoff bundle directory.")
    parser.add_argument("--records", type=Path, help="Verified Data training records JSON file.")
    parser.add_argument("--allowed-output-root", type=Path, help="Explicit non-broad output container root.")
    parser.add_argument("--output-dir", type=Path, help="New non-existing run directory under allowed-output-root.")
    parser.add_argument("--evaluator-version", type=str, help="Pinned evaluator version identifier.")
    parser.add_argument("--evaluator-sha256", type=str, help="Pinned evaluator SHA-256 hex digest.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--engine-sha256", type=str, default=None)
    parser.add_argument("--profile-sha256", type=str, default=None)
    parser.add_argument(
        "--clean-process-verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify published adapter checkpoint in a clean offline subprocess (default: enabled).",
    )
    args = parser.parse_args(argv)

    if args.verify_checkpoint is not None:
        try:
            summary = verify_checkpoint(args.verify_checkpoint, verify_torch_weights=True)
            print(json.dumps(summary))
            return 0
        except MLFailure as err:
            print(json.dumps({"status": "failed", "code": err.code, "stage": err.stage, "production_active": False}))
            return 2
        except Exception:
            print(json.dumps({"status": "failed", "code": "RELOAD_VERIFICATION_FAILED", "stage": "reload", "production_active": False}))
            return 2

    required_train = (
        args.config,
        args.snapshot,
        args.ocr_bundle,
        args.records,
        args.allowed_output_root,
        args.output_dir,
    )
    if any(item is None for item in required_train):
        print(json.dumps({
            "status": "G0_NOT_RUN",
            "error_code": "MISSING_REQUIRED_ARGUMENTS",
            "stage": "config",
            "production_active": False,
            "g0_acceptance_claimed": False,
        }))
        return 2

    result = run_qwen_lora_g0_training(
        config_path=args.config,
        snapshot_dir=args.snapshot,
        ocr_bundle_dir=args.ocr_bundle,
        records_path=args.records,
        allowed_output_root=args.allowed_output_root,
        output_dir=args.output_dir,
        evaluator_version=args.evaluator_version,
        evaluator_sha256=args.evaluator_sha256,
        repository_root=args.repo_root,
        expected_engine_sha256=args.engine_sha256,
        expected_profile_sha256=args.profile_sha256,
        clean_process_verify=args.clean_process_verify,
    )
    print(json.dumps({
        "status": result.status,
        "error_code": result.error_code,
        "stage": result.stage,
        "evidence_scope": result.evidence_scope,
        "steps_completed": result.steps_completed,
        "reload_verified": result.reload_verified,
        "production_active": False,
        "g0_acceptance_claimed": False,
    }))
    if result.status == "G0_COMPLETED":
        return 0
    return 2 if result.status == "G0_NOT_RUN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
