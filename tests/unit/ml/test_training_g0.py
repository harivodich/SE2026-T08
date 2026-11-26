"""Focused offline training machinery tests using tiny synthetic records and fixtures.

SCOPE NOTICE:
These tests verify offline training machinery ONLY (reader/record joins, four-state
label masking, leakage/final-split rejection, opt-in and artifact-pin guards,
finite loss/gradient/parameter-delta checks, atomic checkpoint/run manifests,
clean-process reload verification, corrupt-checkpoint detection, and output path
safety). They provide SYNTHETIC MACHINERY EVIDENCE ONLY — never model quality,
pilot readiness, Qwen3 G0 acceptance, or fine-tune acceptance.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
import pytest

from vietdoc.contracts.ocr import OcrBlock, OcrPage
from vietdoc.data.adapters.labels import FieldLabel, FieldLabels, VERSION as LABEL_VERSION
from vietdoc.ml import model_provision as provision
from vietdoc.ml.ocr_adapter import PROMPT_VERSION, SERIALIZATION_VERSION
from vietdoc.ml.ocr_handoff import export_handoff
from vietdoc.ml.model_loading import QwenLoader
from vietdoc.ml.qwen_config import (
    MLFailure,
    QwenConfig,
    derive_inference_config_for_training,
    load_config,
)
from vietdoc.ml.training_dataset import (
    DataTrainingRecord,
    LABEL_IGNORE_INDEX,
    TrainingCollator,
    data_record_from_sample,
    join_training_dataset,
    load_ocr_handoff_bundle,
)
from vietdoc.ml.training_g0 import (
    ArtifactPins,
    G0TrainingConfig,
    LoRAConfigSpec,
    PeftLoraModelPort,
    TorchModelPort,
    TorchOptimizerPort,
    load_training_config,
    main as g0_cli_main,
    run_g0_training,
    run_qwen_lora_g0_training,
    validate_lora_target_modules,
    validate_output_dir,
    verify_checkpoint,
    verify_checkpoint_in_clean_process,
)
from vietdoc.pipeline.ocr.handoff import review_manifest

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SHA256 = "0948307b0c274d565fbe89b25d69f1692d0d6a4241352939f424ce0eba6b3ded"
HAS_TORCH = importlib.util.find_spec("torch") is not None


class DeterministicStubTokenizer:
    """Tiny byte-level deterministic tokenizer for synthetic machinery tests only."""

    chat_template = "synthetic-test-template"
    eos_token_id = 3
    pad_token_id = 0
    all_special_tokens = ["<|im_start|>", "<|im_end|>", "<think>", "</think>"]
    model_max_length = 40960

    def __len__(self) -> int:
        return 64

    def get_vocab(self) -> dict[str, int]:
        return {f"tok_{i}": i for i in range(len(self))}

    def encode(self, text: str, **kwargs) -> list[int]:
        raw = text.encode("utf-8")
        # Map UTF-8 bytes into [4..63] so 0=pad and 3=eos stay reserved.
        return [4 + (byte % 60) for byte in raw[:48]] or [4]

    def apply_chat_template(self, messages, **kwargs) -> list[int]:
        assert kwargs == dict(
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
            return_dict=False,
        )
        self.last_messages = messages
        return [1, 5, 6, 7, 2]


def _make_qwen_config_dict() -> dict:
    return {
        "model": {
            "id": provision.MODEL_ID,
            "revision": provision.REVISION,
            "tokenizer_revision": provision.REVISION,
            "local_files_only": True,
            "trust_remote_code": False,
            "use_safetensors": True,
        },
        "execution": {
            "enabled": True,
            "allow_download": False,
            "allow_training": False,
            "allow_paid_compute": False,
            "runtime_activation": False,
        },
        "input": {
            "input_profile": "ocr_text_layout_v1",
            "accept_image_input": False,
            "max_input_tokens": 3072,
            "ocr_context": {"max_tokens_when_enabled": 1024},
        },
        "output": {
            "schema_path": "specs/contracts/business.schema.json",
            "schema_sha256": SCHEMA_SHA256,
        },
        "inference": {
            "enable_thinking": False,
            "do_sample": False,
            "num_beams": 1,
            "batch_size": 1,
            "max_new_tokens": 2048,
            "max_sequence_tokens": 5120,
            "selected_profile": "reference_lora",
            "input_profile": "ocr_text_layout_v1",
        },
        "profiles": {
            "reference_lora": {"device": "cpu", "dtype": "float32", "quantization": "none"},
        },
        "training_g0": {
            "input_profile": "ocr_text_layout_v1",
            "observed_ocr_only": True,
            "require_train_inference_serialization_parity": True,
            "seed": 2301,
            "micro_batch_size": 1,
            "gradient_accumulation_steps": 1,
            "max_optimizer_steps": 2,
            "max_grad_norm": 1.0,
            "packing": False,
            "label_ignore_index": -100,
            "truncation": False,
            "independent_dev_and_final_access_in_g0": False,
        },
    }


@pytest.fixture
def qwen_config() -> QwenConfig:
    return QwenConfig.from_mapping(_make_qwen_config_dict(), ROOT)


def _receipt_gold_and_labels(*, extra_status: str | None = None) -> tuple[dict, dict]:
    gold = {
        "merchant_name": "Quán Cà Phê Mẫu",
        "merchant_address": None,
        "transaction_date": "2026-01-02",
        "transaction_time": None,
        "total_amount": "40000",
        "items": [
            {
                "description": "Cà phê sữa",
                "quantity": "2",
                "unit": "ly",
                "unit_price": "20000",
                "line_total": "40000",
            }
        ],
    }
    labels = {
        "/merchant_name": {"status": "present", "raw": "Quán Cà Phê Mẫu", "reason": None},
        "/merchant_address": {"status": "absent", "raw": None, "reason": "Không in địa chỉ."},
        "/transaction_date": {"status": "present", "raw": "02/01/2026", "reason": None},
        "/transaction_time": {"status": "absent", "raw": None, "reason": "Không in giờ."},
        "/total_amount": {"status": "present", "raw": "40.000", "reason": None},
        "/items/0/description": {"status": "present", "raw": "Cà phê sữa", "reason": None},
        "/items/0/quantity": {"status": "present", "raw": "2", "reason": None},
        "/items/0/unit": {"status": "present", "raw": "ly", "reason": None},
        "/items/0/unit_price": {"status": "present", "raw": "20.000", "reason": None},
        "/items/0/line_total": {"status": "present", "raw": "40.000", "reason": None},
    }
    if extra_status == "obscured":
        labels["/merchant_address"] = {"status": "obscured", "raw": None, "reason": "Bị mờ/che khuất."}
    elif extra_status == "unlabeled":
        labels["/transaction_time"] = {"status": "unlabeled", "raw": None, "reason": "Chưa gán nhãn."}
    elif extra_status == "both":
        labels["/merchant_address"] = {"status": "obscured", "raw": None, "reason": "Bị mờ/che khuất."}
        labels["/transaction_time"] = {"status": "unlabeled", "raw": None, "reason": "Chưa gán nhãn."}
    return gold, labels


def _invoice_gold_and_labels() -> tuple[dict, dict]:
    gold = {
        "invoice_number": "MAU-001",
        "issue_date": "2026-01-02",
        "seller_name": "Công ty Mẫu",
        "buyer_name": None,
        "subtotal": "40000",
        "tax_amount": None,
        "discount_amount": None,
        "total_amount": "40000",
        "items": [
            {
                "description": "Cà phê rang",
                "quantity": "2",
                "unit": "gói",
                "unit_price": "20000",
                "line_total": "40000",
            }
        ],
    }
    labels = {
        "/invoice_number": {"status": "present", "raw": "MAU-001", "reason": None},
        "/issue_date": {"status": "present", "raw": "02/01/2026", "reason": None},
        "/seller_name": {"status": "present", "raw": "Công ty Mẫu", "reason": None},
        "/buyer_name": {"status": "absent", "raw": None, "reason": "Không in người mua."},
        "/subtotal": {"status": "present", "raw": "40.000", "reason": None},
        "/tax_amount": {"status": "absent", "raw": None, "reason": "Không thuế."},
        "/discount_amount": {"status": "absent", "raw": None, "reason": "Không giảm giá."},
        "/total_amount": {"status": "present", "raw": "40.000", "reason": None},
        "/items/0/description": {"status": "present", "raw": "Cà phê rang", "reason": None},
        "/items/0/quantity": {"status": "present", "raw": "2", "reason": None},
        "/items/0/unit": {"status": "present", "raw": "gói", "reason": None},
        "/items/0/unit_price": {"status": "present", "raw": "20.000", "reason": None},
        "/items/0/line_total": {"status": "present", "raw": "40.000", "reason": None},
    }
    return gold, labels


def _make_png(color=(255, 255, 255)) -> bytes:
    with Image.new("RGB", (80, 60), color) as img, BytesIO() as buf:
        img.save(buf, format="PNG")
        return buf.getvalue()


def _build_verified_bundle_and_records(
    tmp_path: Path,
    *,
    specs: list[tuple[str, str, str, str | None]] | None = None,
) -> tuple[Path, dict, list[DataTrainingRecord], dict[str, str]]:
    """Build a real AI-1 handoff -> AI-2 OCR bundle + matching synthetic Data records."""
    if specs is None:
        specs = [
            ("rec_train_01", "receipt", "train", None),
            ("inv_train_02", "invoice", "train", None),
        ]

    data_root = tmp_path / "synthetic-data"
    data_root.mkdir(parents=True, exist_ok=True)
    manifest_samples = []
    input_shas: dict[str, str] = {}

    for idx, (sid, doc_type, _split, _status_mode) in enumerate(specs):
        png = _make_png(color=(255 - idx, 250, 245))
        sha = hashlib.sha256(png).hexdigest()
        input_shas[sid] = sha
        (data_root / f"{sid}.png").write_bytes(png)
        # Deliberately write a gold transcript file to verify it never leaks into OCR/prompts.
        (data_root / f"{sid}.txt").write_text(f"FORBIDDEN_GOLD_TRANSCRIPT_{sid}\n", encoding="utf-8")
        manifest_samples.append(
            {
                "sample_id": sid,
                "document_type": doc_type,
                "assets": {"png": {"path": f"{sid}.png", "sha256": sha}},
            }
        )

    manifest_path = data_root / "manifest.json"
    manifest_path.write_text(
        json.dumps({"version": "d2.synthetic-fixture.v1", "samples": manifest_samples}),
        encoding="utf-8",
    )

    engine = Mock()
    engine.load_seconds = 0.05
    engine.last_inference_seconds = 0.02

    def recognize(loaded, *, remaining_budget_ms):
        w, h = loaded.metadata.canonical.width, loaded.metadata.canonical.height
        return OcrPage(
            0,
            w,
            h,
            "synthetic.ocr.v1",
            (
                OcrBlock("p0-b0001", "Quán Cà Phê Mẫu", ((0.1, 0.1), (0.8, 0.1), (0.8, 0.25), (0.1, 0.25)), 0.94, None),
                OcrBlock("p0-b0002", "Tổng: 40.000", ((0.1, 0.4), (0.8, 0.4), (0.8, 0.55), (0.1, 0.55)), 0.91, None),
            ),
        )

    engine.recognize.side_effect = recognize
    handoff_dir = tmp_path / "ai1-handoff"
    review_manifest(data_root, manifest_path, handoff_dir, engine)

    release_dir = tmp_path / "ocr-release"
    release_dir.mkdir(parents=True, exist_ok=True)
    blob = b"synthetic-ocr-engine-bytes"
    engine_manifest_path = release_dir / "engine-manifest.json"
    engine_manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "pipeline_manifest_id": "synthetic-ocr.v1",
                "files": [
                    {
                        "path": "ocr/model.bin",
                        "sha256": hashlib.sha256(blob).hexdigest(),
                        "size_bytes": len(blob),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    bundle_dir = tmp_path / "ai2-ocr-bundle"
    index = export_handoff(handoff_dir, engine_manifest_path, bundle_dir)

    records: list[DataTrainingRecord] = []
    canonical_shas: dict[str, str] = {}
    for idx, (sid, doc_type, split, status_mode) in enumerate(specs):
        if doc_type == "receipt":
            gold, labels = _receipt_gold_and_labels(extra_status=status_mode)
        else:
            gold, labels = _invoice_gold_and_labels()
        canonical_sha = index["samples"][sid]["provenance"]["canonical_sha256"]
        canonical_shas[sid] = canonical_sha
        records.append(
            DataTrainingRecord(
                sample_id=sid,
                base_id=f"base-{sid}",
                family_id=f"{doc_type}-fam-{idx:02d}",
                source_group=f"src-{doc_type}-{idx:02d}",
                assignment_group=f"grp-{doc_type}-{idx:02d}",
                split=split,  # type: ignore[arg-type]
                document_type=doc_type,  # type: ignore[arg-type]
                input_sha256=input_shas[sid],
                canonical_sha256=canonical_sha,
                gold=gold,
                labels=labels,
                content_sha256=hashlib.sha256(f"content-{sid}".encode("utf-8")).hexdigest(),
                population_id="synthetic-pop-v1",
                dataset_manifest_sha256=index["source_manifest_sha256"],
            )
        )
    return bundle_dir, index, records, canonical_shas


def _pins_for(dataset) -> ArtifactPins:
    return ArtifactPins(
        dataset_manifest_sha256=dataset.source_manifest_sha256,
        sample_membership_sha256=dataset.sample_membership_sha256,
        evaluator_version="vietdoc.synthetic-eval.v1",
        evaluator_sha256="e" * 64,
        model_id=provision.MODEL_ID,
        model_revision=provision.REVISION,
        model_manifest_sha256="1" * 64,
        tokenizer_sha256="2" * 64,
        schema_sha256=dataset.schema_sha256,
        ocr_engine_sha256=dataset.engine_sha256,
        ocr_profile_sha256=dataset.profile_sha256,
        serialization_version=dataset.serialization_version,
        serialization_sha256=dataset.serialization_sha256,
        prompt_version=dataset.prompt_version,
        label_adapter_version=dataset.label_adapter_version,
    )


class SyntheticLinearModelPort:
    """Pure-Python deterministic port for testing G0 runner invariants without torch."""

    def __init__(
        self,
        *,
        initial_weights: list[float] | None = None,
        force_loss: float | None = None,
        force_grad: float | None = None,
        probe_bias: float = 0.0,
    ) -> None:
        self.weights = list(initial_weights or [0.25, -0.5, 0.75, 0.1])
        self.grads: list[float] | None = None
        self.force_loss = force_loss
        self.force_grad = force_grad
        self.probe_bias = probe_bias

    def parameter_snapshot(self) -> dict[str, tuple[float, ...]]:
        return {"w": tuple(self.weights)}

    def forward_loss(self, batch) -> float:
        if self.force_loss is not None:
            return self.force_loss
        # Deterministic convex quadratic over supervised tokens.
        supervised = [tok for row in batch.labels for tok in row if tok != batch.label_ignore_index]
        target = sum(supervised) / max(1, len(supervised)) * 0.01
        pred = sum(self.weights)
        return (pred - target) ** 2

    def loss_value(self, loss: float) -> float:
        return loss

    def backward(self, loss: float) -> None:
        if self.force_grad is not None:
            self.grads = [self.force_grad for _ in self.weights]
            return
        scale = 2.0 * (sum(self.weights) - 0.15)
        self.grads = [scale * 0.25 for _ in self.weights]

    def gradient_snapshot(self) -> dict[str, tuple[float, ...]]:
        if self.grads is None:
            return {}
        return {"w": tuple(self.grads)}

    def clip_gradients(self, max_grad_norm: float) -> float:
        assert self.grads is not None
        norm = sum(g * g for g in self.grads) ** 0.5
        if norm > max_grad_norm and norm > 0:
            ratio = max_grad_norm / norm
            self.grads = [g * ratio for g in self.grads]
        return norm

    def zero_grad(self) -> None:
        self.grads = None

    def inference_probe(self, batch) -> list[float]:
        token_sum = sum(batch.input_ids[0]) * 0.001
        return [w + token_sum + self.probe_bias for w in self.weights]

    def save_state(self, checkpoint_dir: Path) -> list[str]:
        raw = (json.dumps({"weights": self.weights}, allow_nan=False) + "\n").encode("utf-8")
        with (checkpoint_dir / "model_state.json").open("xb") as stream:
            stream.write(raw)
        return ["model_state.json"]

    def load_state(self, checkpoint_dir: Path) -> None:
        data = json.loads((checkpoint_dir / "model_state.json").read_text(encoding="utf-8"))
        self.weights = [float(v) for v in data["weights"]]


class SyntheticOptimizerPort:
    def __init__(self, model_port: SyntheticLinearModelPort, *, lr: float = 0.05) -> None:
        self.model_port = model_port
        self.lr = lr
        self.steps = 0

    def step(self) -> None:
        assert self.model_port.grads is not None
        self.model_port.weights = [
            w - self.lr * g for w, g in zip(self.model_port.weights, self.model_port.grads)
        ]
        self.steps += 1

    def zero_grad(self) -> None:
        self.model_port.zero_grad()

    def save_state(self, checkpoint_dir: Path) -> list[str]:
        raw = (json.dumps({"lr": self.lr, "steps": self.steps}, allow_nan=False) + "\n").encode("utf-8")
        with (checkpoint_dir / "optimizer_state.json").open("xb") as stream:
            stream.write(raw)
        return ["optimizer_state.json"]


def _fake_torch_stub(*, cuda_available: bool = False):
    return SimpleNamespace(
        manual_seed=lambda seed: None,
        cuda=SimpleNamespace(
            is_available=lambda: cuda_available,
            device_count=lambda: 1 if cuda_available else 0,
        ),
    )


# ---------------------------------------------------------------------------
# 1. Checked-in config preservation & opt-in guards
# ---------------------------------------------------------------------------


def test_checked_in_qwen_g0_yaml_remains_execution_disabled():
    raw_yaml = (ROOT / "src/vietdoc/ml/configs/qwen-g0.yaml").read_text(encoding="utf-8")
    assert "enabled: false" in raw_yaml
    assert "allow_training: false" in raw_yaml
    assert "allow_download: false" in raw_yaml
    assert "runtime_activation: false" in raw_yaml

    mapping = _make_qwen_config_dict()
    mapping["execution"]["enabled"] = False
    mapping["execution"]["allow_training"] = False
    cfg = G0TrainingConfig.from_mapping(mapping, ROOT)
    assert cfg.execution_enabled is False
    assert cfg.allow_training is False
    assert cfg.runtime_activation is False


@pytest.mark.parametrize(
    "flag,value",
    [
        ("allow_download", True),
        ("allow_paid_compute", True),
        ("runtime_activation", True),
    ],
)
def test_g0_config_rejects_forbidden_execution_modes(flag, value):
    mapping = _make_qwen_config_dict()
    mapping["execution"][flag] = value
    with pytest.raises(MLFailure, match="CONFIG_INVALID"):
        G0TrainingConfig.from_mapping(mapping, ROOT)


# ---------------------------------------------------------------------------
# 2. Reader/record adapter: ID/hash joins, provenance, type, no gold in OCR
# ---------------------------------------------------------------------------


def test_join_verified_handoff_and_data_records_with_four_state_and_prompt_parity(tmp_path, qwen_config):
    bundle_dir, index, records, canonical_shas = _build_verified_bundle_and_records(tmp_path)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        qwen_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
        expected_dataset_manifest_sha256=index["source_manifest_sha256"],
        expected_canonical_sha256s=canonical_shas,
        target_split="train",
    )

    assert dataset.counts == {"joined": 2, "eligible": 2, "excluded": 0, "receipt": 1, "invoice": 1}
    assert dataset.status_totals["present"] > 0
    assert dataset.status_totals["absent"] > 0
    assert dataset.status_totals["obscured"] == 0
    assert dataset.status_totals["unlabeled"] == 0
    assert set(dataset.status_totals) == {"present", "absent", "obscured", "unlabeled"}
    assert dataset.serialization_version == SERIALIZATION_VERSION
    assert dataset.prompt_version == PROMPT_VERSION
    assert dataset.label_adapter_version == LABEL_VERSION

    tok = DeterministicStubTokenizer()
    collator = TrainingCollator(qwen_config, tok)
    batch = collator.collate(dataset.examples)
    assert batch.sample_ids == ("rec_train_01", "inv_train_02")
    assert batch.document_types == ("receipt", "invoice")
    assert batch.label_ignore_index == LABEL_IGNORE_INDEX

    # Verify prompt/OCR/padding tokens are masked to -100 and assistant target + EOS are supervised.
    for row_idx in range(len(batch.sample_ids)):
        prompt_len = batch.prompt_lengths[row_idx]
        target_len = batch.target_lengths[row_idx]
        seq_ids = batch.input_ids[row_idx]
        seq_mask = batch.attention_mask[row_idx]
        seq_labels = batch.labels[row_idx]
        assert all(lbl == LABEL_IGNORE_INDEX for lbl in seq_labels[:prompt_len])
        assert seq_labels[prompt_len : prompt_len + target_len] == seq_ids[prompt_len : prompt_len + target_len]
        assert seq_labels[prompt_len + target_len - 1] == tok.eos_token_id
        assert all(m == 1 for m in seq_mask[: prompt_len + target_len])
        assert all(m == 0 for m in seq_mask[prompt_len + target_len :])
        assert all(lbl == LABEL_IGNORE_INDEX for lbl in seq_labels[prompt_len + target_len :])

    # Verify gold transcript never entered prompt messages.
    prompt_blob = json.dumps(tok.last_messages, ensure_ascii=False)
    assert "FORBIDDEN_GOLD_TRANSCRIPT" not in prompt_blob
    assert "label_statuses" not in prompt_blob


def test_four_state_obscured_and_unlabeled_are_distinct_excluded_and_blocked_from_collator(tmp_path, qwen_config):
    specs = [
        ("rec_clean", "receipt", "train", None),
        ("rec_obscured", "receipt", "train", "obscured"),
        ("rec_unlabeled", "receipt", "train", "unlabeled"),
        ("rec_both", "receipt", "train", "both"),
    ]
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path, specs=specs)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        qwen_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
        target_split="train",
    )

    assert [ex.sample_id for ex in dataset.examples] == ["rec_clean"]
    assert dataset.counts == {"joined": 4, "eligible": 1, "excluded": 3, "receipt": 1, "invoice": 0}
    assert dataset.status_totals["present"] > 0
    assert dataset.status_totals["absent"] > 0
    assert dataset.status_totals["obscured"] == 2
    assert dataset.status_totals["unlabeled"] == 2

    excluded_by_id = {item.sample_id: item for item in dataset.excluded}
    assert excluded_by_id["rec_obscured"].reason == "OBSCURED_FIELDS_EXCLUDED"
    assert excluded_by_id["rec_obscured"].obscured_pointers == ("/merchant_address",)
    assert excluded_by_id["rec_obscured"].unlabeled_pointers == ()

    assert excluded_by_id["rec_unlabeled"].reason == "UNLABELED_FIELDS_EXCLUDED"
    assert excluded_by_id["rec_unlabeled"].obscured_pointers == ()
    assert excluded_by_id["rec_unlabeled"].unlabeled_pointers == ("/transaction_time",)

    assert excluded_by_id["rec_both"].reason == "OBSCURED_AND_UNLABELED_FIELDS_EXCLUDED"
    assert excluded_by_id["rec_both"].obscured_pointers == ("/merchant_address",)
    assert excluded_by_id["rec_both"].unlabeled_pointers == ("/transaction_time",)

    # Defense in depth: collator must reject an obscured record even if forced directly.
    collator = TrainingCollator(qwen_config, DeterministicStubTokenizer())
    clean_rec = dataset.examples[0]
    tampered_fields = tuple(
        FieldLabel(fl.pointer, fl.value, "obscured" if fl.pointer == "/merchant_address" else fl.status)
        for fl in clean_rec.field_labels.fields
    )
    forced_obscured = replace(
        clean_rec,
        field_labels=FieldLabels(LABEL_VERSION, tampered_fields),
        status_counts={**clean_rec.status_counts, "absent": 1, "obscured": 1},
    )
    with pytest.raises(MLFailure, match="UNSUPERVISABLE_LABEL_STATUS"):
        collator.collate([forced_obscured])


@pytest.mark.parametrize(
    "case,expected_code",
    [
        ("missing_data_id", "SAMPLE_ID_JOIN_MISMATCH"),
        ("extra_data_id", "SAMPLE_ID_JOIN_MISMATCH"),
        ("duplicate_exact_id", "DUPLICATE_SAMPLE_ID"),
        ("duplicate_casefold_id", "DUPLICATE_SAMPLE_ID"),
        ("wrong_input_sha", "PROVENANCE_MISMATCH"),
        ("wrong_canonical_sha", "PROVENANCE_MISMATCH"),
        ("wrong_engine_sha", "PROVENANCE_MISMATCH"),
        ("wrong_profile_sha", "PROVENANCE_MISMATCH"),
        ("missing_engine_pin", "ARTIFACT_PINS_MISSING"),
        ("wrong_document_type", "DOCUMENT_TYPE_MISMATCH"),
        ("invalid_gold_schema", "GOLD_SCHEMA_INVALID"),
        ("invalid_label_status_mismatch", "LABEL_STATUS_INVALID"),
        ("gold_in_ocr_input", "GOLD_IN_OCR_INPUT"),
        ("tampered_bundle_ocr_hash", "OCR_HANDOFF_HASH_MISMATCH"),
    ],
)
def test_join_rejects_id_hash_provenance_type_and_gold_in_ocr_violations(
    tmp_path, qwen_config, case, expected_code
):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    engine_sha = index["engine_manifest"]["engine_sha256"]
    profile_sha = index["profile"]["profile_sha256"]
    ocr_source: Path | object = bundle_dir

    if case == "missing_data_id":
        records = records[:1]
    elif case == "extra_data_id":
        records.append(replace(records[0], sample_id="extra_unmatched_99", base_id="base-extra"))
    elif case == "duplicate_exact_id":
        records.append(records[0])
    elif case == "duplicate_casefold_id":
        records[1] = replace(records[1], sample_id=records[0].sample_id.upper())
    elif case == "wrong_input_sha":
        records[0] = replace(records[0], input_sha256="0" * 64)
    elif case == "wrong_canonical_sha":
        records[0] = replace(records[0], canonical_sha256="f" * 64)
    elif case == "wrong_engine_sha":
        engine_sha = "9" * 64
    elif case == "wrong_profile_sha":
        profile_sha = "8" * 64
    elif case == "missing_engine_pin":
        engine_sha = ""
    elif case == "wrong_document_type":
        inv_gold, inv_labels = _invoice_gold_and_labels()
        records[0] = replace(records[0], document_type="invoice", gold=inv_gold, labels=inv_labels)
    elif case == "invalid_gold_schema":
        bad_gold = deepcopy(records[0].gold)
        bad_gold["total_amount"] = "not-a-decimal"
        records[0] = replace(records[0], gold=bad_gold)
    elif case == "invalid_label_status_mismatch":
        bad_labels = deepcopy(records[0].labels)
        assert isinstance(bad_labels, dict)
        bad_labels["/merchant_address"] = {"status": "present", "raw": "Fake", "reason": None}
        records[0] = replace(records[0], labels=bad_labels)
    elif case == "gold_in_ocr_input":
        loaded_bundle = load_ocr_handoff_bundle(bundle_dir)
        mutated_samples = dict(loaded_bundle.samples)
        s0 = mutated_samples["rec_train_01"]
        mutated_samples["rec_train_01"] = replace(s0, ocr={**s0.ocr, "gold_transcript": "LEAKED"})
        ocr_source = replace(loaded_bundle, samples=mutated_samples)
    elif case == "tampered_bundle_ocr_hash":
        ocr_file = bundle_dir / "rec_train_01" / "ocr.json"
        ocr_file.write_text(ocr_file.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(MLFailure, match=expected_code):
        join_training_dataset(
            ocr_source,  # type: ignore[arg-type]
            records,
            qwen_config,
            expected_engine_sha256=engine_sha,
            expected_profile_sha256=profile_sha,
            target_split="train",
        )


def test_data_record_from_sample_fails_closed_when_split_or_lineage_missing():
    gold, labels = _receipt_gold_and_labels()
    # D1.2-style sample missing split/source_group must fail closed.
    incomplete_sample = {
        "sample_id": "d12-receipt-03",
        "base_id": "d12-receipt-03",
        "family_id": "receipt-layout-0",
        "document_type": "receipt",
        "assets": {"png": {"path": "d12-receipt-03.png", "sha256": "a" * 64}},
    }
    with pytest.raises(MLFailure, match="DATA_RECORD_INVALID"):
        data_record_from_sample(incomplete_sample, gold, labels)


# ---------------------------------------------------------------------------
# 3. Leakage and final-split rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leak_kind,expected_code",
    [
        ("target_split_final", "FINAL_SPLIT_FORBIDDEN"),
        ("record_in_final_split", "FINAL_SPLIT_FORBIDDEN"),
        ("reference_in_final_split", "FINAL_SPLIT_FORBIDDEN"),
        ("mixed_train_and_dev", "CROSS_POPULATION_LEAKAGE"),
        ("mismatched_population_id", "CROSS_POPULATION_LEAKAGE"),
        ("mismatched_dataset_manifest", "CROSS_POPULATION_LEAKAGE"),
        ("cross_split_base_id", "CROSS_POPULATION_LEAKAGE"),
        ("cross_split_family_id", "CROSS_POPULATION_LEAKAGE"),
        ("cross_split_source_group", "CROSS_POPULATION_LEAKAGE"),
        ("cross_split_input_sha256", "CROSS_POPULATION_LEAKAGE"),
        ("cross_split_content_sha256", "CROSS_POPULATION_LEAKAGE"),
    ],
)
def test_leakage_and_final_split_rejected(tmp_path, qwen_config, leak_kind, expected_code):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    target_split: str = "train"
    reference_records: list[DataTrainingRecord] | None = None

    dev_ref = DataTrainingRecord(
        sample_id="dev_ref_01",
        base_id="base-dev-01",
        family_id="receipt-fam-dev-99",
        source_group="src-dev-99",
        assignment_group="grp-dev-99",
        split="dev",
        document_type="receipt",
        input_sha256="c" * 64,
        gold=records[0].gold,
        labels=records[0].labels,
        content_sha256="d" * 64,
        population_id="synthetic-pop-v1",
    )

    if leak_kind == "target_split_final":
        target_split = "final"
    elif leak_kind == "record_in_final_split":
        records[1] = replace(records[1], split="final")
    elif leak_kind == "reference_in_final_split":
        reference_records = [replace(dev_ref, split="final")]
    elif leak_kind == "mixed_train_and_dev":
        records[1] = replace(records[1], split="dev")
    elif leak_kind == "mismatched_population_id":
        records[1] = replace(records[1], population_id="other-population-v2")
    elif leak_kind == "mismatched_dataset_manifest":
        records[1] = replace(records[1], dataset_manifest_sha256="7" * 64)
    elif leak_kind == "cross_split_base_id":
        reference_records = [replace(dev_ref, base_id=records[0].base_id)]
    elif leak_kind == "cross_split_family_id":
        reference_records = [replace(dev_ref, family_id=records[0].family_id)]
    elif leak_kind == "cross_split_source_group":
        reference_records = [replace(dev_ref, source_group=records[0].source_group)]
    elif leak_kind == "cross_split_input_sha256":
        reference_records = [replace(dev_ref, input_sha256=records[0].input_sha256)]
    elif leak_kind == "cross_split_content_sha256":
        reference_records = [replace(dev_ref, content_sha256=records[0].content_sha256)]

    with pytest.raises(MLFailure, match=expected_code):
        join_training_dataset(
            bundle_dir,
            records,
            qwen_config,
            expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
            expected_profile_sha256=index["profile"]["profile_sha256"],
            target_split=target_split,  # type: ignore[arg-type]
            reference_records=reference_records,
        )


def test_collator_rejects_sequence_overflow_without_truncation(tmp_path, qwen_config):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    tight_config = replace(qwen_config, max_new_tokens=5, max_sequence_tokens=10)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        tight_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
    )
    collator = TrainingCollator(tight_config, DeterministicStubTokenizer())
    with pytest.raises(MLFailure, match="CONTEXT_OVERFLOW"):
        collator.collate(dataset.examples[:1])


# ---------------------------------------------------------------------------
# 4. G0 runner: missing torch, missing pins, finite loss/grad/delta,
#    atomic checkpoint, clean-process reload, corruption, output path safety
# ---------------------------------------------------------------------------


def test_missing_torch_returns_typed_not_run_never_fake_pass(tmp_path, qwen_config, monkeypatch):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        qwen_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
    )
    out_root = tmp_path / "runs"
    out_root.mkdir()
    model_port = SyntheticLinearModelPort()
    opt_port = SyntheticOptimizerPort(model_port)
    collator = TrainingCollator(qwen_config, DeterministicStubTokenizer())

    monkeypatch.setitem(sys.modules, "torch", None)
    result = run_g0_training(
        config=G0TrainingConfig(execution_enabled=True, allow_training=True, seed=2301),
        pins=_pins_for(dataset),
        dataset=dataset,
        collator=collator,
        model_port=model_port,
        optimizer_port=opt_port,
        allowed_output_root=out_root,
        output_dir=out_root / "run-no-torch",
    )
    assert result.status == "G0_NOT_RUN"
    assert result.error_code == "TRAINING_DEPENDENCY_MISSING"
    assert result.stage == "dependency"
    assert result.reload_verified is False
    assert result.production_active is False
    assert result.g0_acceptance_claimed is False
    assert not (out_root / "run-no-torch").exists()


@pytest.mark.parametrize(
    "missing_pin",
    [
        "dataset_manifest_sha256",
        "sample_membership_sha256",
        "evaluator_sha256",
        "model_manifest_sha256",
        "tokenizer_sha256",
        "serialization_sha256",
        "ocr_engine_sha256",
        "ocr_profile_sha256",
    ],
)
def test_missing_artifact_pins_fail_closed(tmp_path, qwen_config, missing_pin):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        qwen_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
    )
    out_root = tmp_path / "runs"
    out_root.mkdir()
    pins = replace(_pins_for(dataset), **{missing_pin: None})
    model_port = SyntheticLinearModelPort()
    result = run_g0_training(
        config=G0TrainingConfig(execution_enabled=True, allow_training=True, seed=2301),
        pins=pins,
        dataset=dataset,
        collator=TrainingCollator(qwen_config, DeterministicStubTokenizer()),
        model_port=model_port,
        optimizer_port=SyntheticOptimizerPort(model_port),
        allowed_output_root=out_root,
        output_dir=out_root / f"missing-{missing_pin}",
        torch_loader=_fake_torch_stub,
    )
    assert result.status == "G0_NOT_RUN"
    assert result.error_code == "ARTIFACT_PINS_MISSING"
    assert result.stage == "pins"
    assert not (out_root / f"missing-{missing_pin}").exists()


def test_explicit_cuda_request_fails_without_silent_cpu_fallback(tmp_path, qwen_config):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        qwen_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
    )
    out_root = tmp_path / "runs"
    out_root.mkdir()
    model_port = SyntheticLinearModelPort()
    result = run_g0_training(
        config=G0TrainingConfig(
            execution_enabled=True,
            allow_training=True,
            device="cuda:0",
            dtype="bfloat16",
            seed=2301,
        ),
        pins=_pins_for(dataset),
        dataset=dataset,
        collator=TrainingCollator(qwen_config, DeterministicStubTokenizer()),
        model_port=model_port,
        optimizer_port=SyntheticOptimizerPort(model_port),
        allowed_output_root=out_root,
        output_dir=out_root / "cuda-unavailable",
        torch_loader=lambda: _fake_torch_stub(cuda_available=False),
    )
    assert result.status == "G0_NOT_RUN"
    assert result.error_code == "DEVICE_UNAVAILABLE"
    assert not (out_root / "cuda-unavailable").exists()


def test_g0_synthetic_machinery_step_delta_atomic_checkpoint_and_clean_process_reload(tmp_path, qwen_config):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        qwen_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
    )
    out_root = tmp_path / "runs"
    out_root.mkdir()
    run_dir = out_root / "g0-synthetic-01"
    model_port = SyntheticLinearModelPort()
    opt_port = SyntheticOptimizerPort(model_port, lr=0.05)

    result = run_g0_training(
        config=G0TrainingConfig(
            execution_enabled=True,
            allow_training=True,
            seed=2301,
            micro_batch_size=1,
            gradient_accumulation_steps=2,
            max_optimizer_steps=2,
            evidence_scope="synthetic_machinery_only",
        ),
        pins=_pins_for(dataset),
        dataset=dataset,
        collator=TrainingCollator(qwen_config, DeterministicStubTokenizer()),
        model_port=model_port,
        optimizer_port=opt_port,
        allowed_output_root=out_root,
        output_dir=run_dir,
        fresh_model_factory=lambda: SyntheticLinearModelPort(initial_weights=[0.0, 0.0, 0.0, 0.0]),
        clean_process_verify=True,
        torch_loader=_fake_torch_stub,
    )

    assert result.status == "G0_COMPLETED"
    assert result.error_code is None
    assert result.evidence_scope == "synthetic_machinery_only"
    assert result.g0_acceptance_claimed is False
    assert result.production_active is False
    assert result.steps_completed == 2
    assert len(result.loss_history) == 2
    assert result.parameter_delta_l2 is not None and result.parameter_delta_l2 > 0.0
    assert result.parameter_delta_max_abs is not None and result.parameter_delta_max_abs > 0.0
    assert result.reload_verified is True
    assert result.reload_max_output_diff == 0.0
    assert result.run_manifest_path == run_dir / "run_manifest.json"

    run_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["seed"] == 2301
    assert run_manifest["evidence_scope"] == "synthetic_machinery_only"
    assert run_manifest["g0_acceptance_claimed"] is False
    assert run_manifest["production_active"] is False
    assert run_manifest["serving_activated"] is False
    for hash_key in (
        "dataset_manifest_sha256",
        "sample_membership_sha256",
        "evaluator_sha256",
        "model_manifest_sha256",
        "tokenizer_sha256",
        "schema_sha256",
        "ocr_engine_sha256",
        "ocr_profile_sha256",
        "serialization_sha256",
    ):
        assert len(run_manifest["pins"][hash_key]) == 64

    # Corrupt checkpoint / hash tampering must fail closed both in-process and in clean process.
    state_file = run_dir / "checkpoint" / "model_state.json"
    original_bytes = state_file.read_bytes()
    state_file.write_bytes(original_bytes + b" ")
    with pytest.raises(MLFailure, match="CHECKPOINT_HASH_MISMATCH"):
        verify_checkpoint(run_dir)
    with pytest.raises(MLFailure, match="RELOAD_VERIFICATION_FAILED"):
        verify_checkpoint_in_clean_process(run_dir)
    assert g0_cli_main(["--verify-checkpoint", str(run_dir)]) == 2

    # Restore valid state, then verify extra unexpected file is rejected.
    state_file.write_bytes(original_bytes)
    assert verify_checkpoint(run_dir)["status"] == "verified"
    extra_file = run_dir / "checkpoint" / "rogue.bin"
    extra_file.write_bytes(b"rogue")
    with pytest.raises(MLFailure, match="CHECKPOINT_UNEXPECTED_FILES"):
        verify_checkpoint(run_dir)


@pytest.mark.parametrize(
    "failure_mode,expected_code",
    [
        ("nan_loss", "NONFINITE_LOSS"),
        ("inf_loss", "NONFINITE_LOSS"),
        ("nan_grad", "NONFINITE_GRADIENT"),
        ("zero_delta", "ZERO_PARAMETER_DELTA"),
        ("reload_mismatch", "RELOAD_VERIFICATION_FAILED"),
    ],
)
def test_g0_rejects_nonfinite_loss_grad_zero_delta_and_reload_mismatch(
    tmp_path, qwen_config, failure_mode, expected_code
):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        qwen_config,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
    )
    out_root = tmp_path / "runs"
    out_root.mkdir()
    run_dir = out_root / f"fail-{failure_mode}"

    force_loss = float("nan") if failure_mode == "nan_loss" else float("inf") if failure_mode == "inf_loss" else None
    force_grad = float("nan") if failure_mode == "nan_grad" else None
    lr = 0.0 if failure_mode == "zero_delta" else 0.05
    probe_bias = 0.5 if failure_mode == "reload_mismatch" else 0.0

    model_port = SyntheticLinearModelPort(force_loss=force_loss, force_grad=force_grad)
    result = run_g0_training(
        config=G0TrainingConfig(execution_enabled=True, allow_training=True, seed=2301),
        pins=_pins_for(dataset),
        dataset=dataset,
        collator=TrainingCollator(qwen_config, DeterministicStubTokenizer()),
        model_port=model_port,
        optimizer_port=SyntheticOptimizerPort(model_port, lr=lr),
        allowed_output_root=out_root,
        output_dir=run_dir,
        fresh_model_factory=lambda: SyntheticLinearModelPort(probe_bias=probe_bias),
        clean_process_verify=(failure_mode == "reload_mismatch"),
        torch_loader=_fake_torch_stub,
    )
    assert result.status == "G0_FAILED"
    assert result.error_code == expected_code
    assert result.reload_verified is False
    if failure_mode != "reload_mismatch":
        assert not run_dir.exists()


def test_output_path_safety_rejects_broad_traversal_existing_and_symlink_paths(tmp_path, monkeypatch):
    out_root = tmp_path / "allowed"
    out_root.mkdir()

    # Broad roots: filesystem root, repo root, home directory.
    fs_root = Path(out_root.anchor)
    with pytest.raises(MLFailure, match="UNSAFE_OUTPUT_PATH"):
        validate_output_dir(fs_root, fs_root / "run-1")
    with pytest.raises(MLFailure, match="UNSAFE_OUTPUT_PATH"):
        validate_output_dir(ROOT, ROOT / "run-1")
    with pytest.raises(MLFailure, match="UNSAFE_OUTPUT_PATH"):
        validate_output_dir(Path.home(), Path.home() / "run-1")

    # Traversal / outside / equal to root / bad name.
    for bad_target in (
        Path("../escape"),
        tmp_path / "outside-run",
        out_root,
        out_root / "bad name with spaces",
        out_root / ".hidden-run",
    ):
        with pytest.raises(MLFailure, match="UNSAFE_OUTPUT_PATH"):
            validate_output_dir(out_root, bad_target)

    # Existing output directory must never be overwritten.
    existing = out_root / "existing-run"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_bytes(b"keep-me")
    with pytest.raises(MLFailure, match="OUTPUT_EXISTS"):
        validate_output_dir(out_root, existing)
    assert sentinel.read_bytes() == b"keep-me"

    # Symlinked output directory or ancestor must be rejected without skipping on Windows.
    target = tmp_path / "real-dir"
    target.mkdir()
    link_dir = out_root / "link-run"
    try:
        link_dir.symlink_to(target, target_is_directory=True)
    except OSError:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p == link_dir or original(p))
    with pytest.raises(MLFailure, match="UNSAFE_OUTPUT_PATH"):
        validate_output_dir(out_root, link_dir)


# ---------------------------------------------------------------------------
# 5. Conditional real tiny PyTorch model tests (collected ONLY when torch is installed;
#    zero skipped tests in environments without torch).
# ---------------------------------------------------------------------------


if HAS_TORCH:
    import torch

    class TinySyntheticCausalLM(torch.nn.Module):
        """Tiny CPU-only torch module for synthetic G0 machinery verification ONLY."""

        def __init__(self, vocab_size: int = 64, hidden: int = 16) -> None:
            super().__init__()
            self.embed = torch.nn.Embedding(vocab_size, hidden)
            self.head = torch.nn.Linear(hidden, vocab_size)

        def forward(self, input_ids, attention_mask=None, labels=None):
            return self.head(self.embed(input_ids))

    def test_tiny_torch_model_g0_train_step_checkpoint_and_clean_process_reload(tmp_path, qwen_config):
        """Real PyTorch autograd/update/checkpoint/clean-process reload on tiny synthetic model.

        Synthetic machinery evidence ONLY — NOT Qwen3 G0 or extraction quality acceptance.
        """
        bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
        dataset = join_training_dataset(
            bundle_dir,
            records,
            qwen_config,
            expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
            expected_profile_sha256=index["profile"]["profile_sha256"],
        )
        out_root = tmp_path / "torch-runs"
        out_root.mkdir()
        run_dir = out_root / "tiny-torch-g0"

        torch.manual_seed(2301)
        model = TinySyntheticCausalLM(vocab_size=64, hidden=16)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-2)
        model_port = TorchModelPort(model, device="cpu")
        opt_port = TorchOptimizerPort(optimizer)

        result = run_g0_training(
            config=G0TrainingConfig(
                execution_enabled=True,
                allow_training=True,
                device="cpu",
                dtype="float32",
                seed=2301,
                micro_batch_size=1,
                gradient_accumulation_steps=2,
                max_optimizer_steps=2,
                max_grad_norm=1.0,
                reload_tolerance=1e-6,
                evidence_scope="synthetic_machinery_only",
            ),
            pins=_pins_for(dataset),
            dataset=dataset,
            collator=TrainingCollator(qwen_config, DeterministicStubTokenizer()),
            model_port=model_port,
            optimizer_port=opt_port,
            allowed_output_root=out_root,
            output_dir=run_dir,
            fresh_model_factory=lambda: TorchModelPort(TinySyntheticCausalLM(vocab_size=64, hidden=16), device="cpu"),
            clean_process_verify=True,
        )

        assert result.status == "G0_COMPLETED"
        assert result.error_code is None
        assert result.evidence_scope == "synthetic_machinery_only"
        assert result.g0_acceptance_claimed is False
        assert result.production_active is False
        assert result.steps_completed == 2
        assert result.parameter_delta_l2 is not None and result.parameter_delta_l2 > 0.0
        assert result.parameter_delta_max_abs is not None and result.parameter_delta_max_abs > 0.0
        assert result.reload_verified is True
        assert result.reload_max_output_diff is not None and result.reload_max_output_diff <= 1e-6

        verified = verify_checkpoint_in_clean_process(
            run_dir,
            expected_checkpoint_manifest_sha256=result.checkpoint_manifest_sha256,
            expected_run_manifest_sha256=result.run_manifest_sha256,
            expect_torch_weights=True,
        )
        assert verified["torch_weights_verified"] is True
        assert verified["parameter_count"] > 0

        # Flip one byte in weights.pt -> must fail both in-process and clean-process verification.
        weights_file = run_dir / "checkpoint" / "weights.pt"
        raw = bytearray(weights_file.read_bytes())
        raw[-1] ^= 0xFF
        weights_file.write_bytes(bytes(raw))
        with pytest.raises(MLFailure, match="CHECKPOINT_HASH_MISMATCH"):
            verify_checkpoint(run_dir, verify_torch_weights=True)
        with pytest.raises(MLFailure, match="RELOAD_VERIFICATION_FAILED"):
            verify_checkpoint_in_clean_process(run_dir, expect_torch_weights=True)


# ---------------------------------------------------------------------------
# 6. Seam S-02 & S-03 regressions: training-vs-inference config split,
#    bounded PEFT/LoRA entrypoint, and adapter-only save/reload verification
#    (pure-Python deterministic doubles; no torch/transformers/peft required).
# ---------------------------------------------------------------------------


def _write_minimal_f32_safetensors(path: Path, tensors: dict[str, tuple[list[int], list[float]]]) -> None:
    import struct

    header: dict[str, dict] = {}
    payload = bytearray()
    cursor = 0
    for name in sorted(tensors):
        shape, values = tensors[name]
        packed = struct.pack(f"<{len(values)}f", *values)
        header[name] = {
            "dtype": "F32",
            "shape": shape,
            "data_offsets": [cursor, cursor + len(packed)],
        }
        payload.extend(packed)
        cursor += len(packed)
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    with path.open("wb") as stream:
        stream.write(struct.pack("<Q", len(header_bytes)))
        stream.write(header_bytes)
        stream.write(payload)


def _read_minimal_f32_safetensors(path: Path) -> dict[str, tuple[list[int], list[float]]]:
    import struct

    with path.open("rb") as stream:
        header_len = struct.unpack("<Q", stream.read(8))[0]
        header = json.loads(stream.read(header_len).decode("utf-8"))
        payload = stream.read()
    out: dict[str, tuple[list[int], list[float]]] = {}
    for name, info in header.items():
        if name == "__metadata__":
            continue
        start, end = info["data_offsets"]
        raw = payload[start:end]
        count = len(raw) // 4
        out[name] = (info["shape"], list(struct.unpack(f"<{count}f", raw)))
    return out


class _FakeTensor:
    """Minimal numeric tensor double for pure-Python PEFT/LoRA entrypoint tests."""

    def __init__(self, values: list[float], *, shape: list[int] | None = None, requires_grad: bool = False) -> None:
        self._values = [float(v) for v in values]
        self.shape = tuple(shape if shape is not None else [len(self._values)])
        self.dtype = "torch.float32"
        self.requires_grad = requires_grad
        self.grad: _FakeTensor | None = None

    def detach(self) -> "_FakeTensor":
        return self

    def to(self, device=None, dtype=None) -> "_FakeTensor":
        return self

    def contiguous(self) -> "_FakeTensor":
        return self

    def reshape(self, *dims) -> "_FakeTensor":
        return self

    def tolist(self) -> list[float]:
        return list(self._values)

    def cpu(self) -> "_FakeTensor":
        return self

    def item(self) -> float:
        return float(self._values[0])

    def __getitem__(self, item):
        if isinstance(item, slice):
            return _FakeTensor(self._values[item])
        return self._values[item]

    def __len__(self) -> int:
        return len(self._values)


class _FakeLoss:
    def __init__(self, value: float, model: "_FakePeftModel") -> None:
        self._value = value
        self._model = model

    def detach(self):
        return self

    def cpu(self):
        return self

    def item(self) -> float:
        return float(self._value)

    def backward(self) -> None:
        for name, param in self._model.named_parameters():
            if param.requires_grad:
                param.grad = _FakeTensor([0.25 * (v + 0.5) for v in param._values], shape=list(param.shape))


class _FakeBaseModel:
    def __init__(self, *, module_names: list[str] | None = None) -> None:
        self.config = SimpleNamespace(use_cache=True)
        self.gradient_checkpointing_enabled = False
        self._module_names = module_names or [
            "model.embed_tokens",
            "model.layers.0.self_attn.q_proj",
            "model.layers.0.self_attn.k_proj",
            "model.layers.0.self_attn.v_proj",
            "model.layers.0.self_attn.o_proj",
            "lm_head",
        ]
        self._base_params = {
            "model.embed_tokens.weight": _FakeTensor([1.0, 2.0], shape=[2], requires_grad=True),
            "model.layers.0.self_attn.q_proj.weight": _FakeTensor([0.5, -0.5], shape=[2], requires_grad=True),
            "lm_head.weight": _FakeTensor([0.1, 0.2], shape=[2], requires_grad=True),
        }

    def gradient_checkpointing_enable(self) -> None:
        self.gradient_checkpointing_enabled = True

    def named_modules(self):
        yield "", self
        for name in self._module_names:
            yield name, SimpleNamespace()

    def named_parameters(self):
        yield from self._base_params.items()


class _FakePeftModel:
    def __init__(self, base_model: _FakeBaseModel, lora_cfg: SimpleNamespace) -> None:
        self.base_model = base_model
        self.lora_cfg = lora_cfg
        self._adapter_params = {
            "base_model.model.model.layers.0.self_attn.q_proj.lora_A.default.weight": _FakeTensor(
                [0.2, -0.1, 0.3, 0.4], shape=[2, 2], requires_grad=True
            ),
            "base_model.model.model.layers.0.self_attn.q_proj.lora_B.default.weight": _FakeTensor(
                [0.05, 0.15, -0.1, 0.25], shape=[2, 2], requires_grad=True
            ),
        }
        self._train_mode = True
        self.device = "cpu"

    def train(self) -> None:
        self._train_mode = True

    def eval(self) -> None:
        self._train_mode = False

    def to(self, device: str) -> "_FakePeftModel":
        self.device = device
        return self

    def named_parameters(self):
        for name, param in self.base_model.named_parameters():
            yield f"base_model.model.{name}", param
        yield from self._adapter_params.items()

    def parameters(self):
        return [param for _name, param in self.named_parameters()]

    def zero_grad(self, set_to_none: bool = True) -> None:
        for _name, param in self.named_parameters():
            param.grad = None

    def __call__(self, *, input_ids, attention_mask=None, labels=None):
        a = self._adapter_params["base_model.model.model.layers.0.self_attn.q_proj.lora_A.default.weight"]._values
        b = self._adapter_params["base_model.model.model.layers.0.self_attn.q_proj.lora_B.default.weight"]._values
        if labels is not None:
            val = sum((x - 0.1) ** 2 for x in a) + sum((y + 0.2) ** 2 for y in b)
            return SimpleNamespace(loss=_FakeLoss(val, self))
        flat_ids = input_ids._values if isinstance(input_ids, _FakeTensor) else [1.0]
        scale = sum(flat_ids) * 0.001
        return SimpleNamespace(logits=_FakeTensor([x + y + scale for x, y in zip(a, b)]))

    def save_pretrained(self, save_directory: str, *, safe_serialization: bool = True) -> None:
        assert safe_serialization is True
        target = Path(save_directory)
        target.mkdir(parents=True, exist_ok=True)
        (target / "adapter_config.json").write_text(
            json.dumps(
                {
                    "peft_type": "LORA",
                    "task_type": self.lora_cfg.task_type,
                    "r": self.lora_cfg.r,
                    "lora_alpha": self.lora_cfg.lora_alpha,
                    "lora_dropout": self.lora_cfg.lora_dropout,
                    "bias": self.lora_cfg.bias,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        tensors = {
            name.replace(".default.", "."): (list(param.shape), list(param._values))
            for name, param in self._adapter_params.items()
        }
        _write_minimal_f32_safetensors(target / "adapter_model.safetensors", tensors)


class _FakeAdamW:
    def __init__(self, params, *, lr: float = 1e-4, weight_decay: float = 0.0) -> None:
        self._params = list(params)
        self.param_groups = [{"params": self._params, "lr": lr, "weight_decay": weight_decay}]

    def zero_grad(self, set_to_none: bool = True) -> None:
        for p in self._params:
            p.grad = None

    def step(self) -> None:
        lr = self.param_groups[0]["lr"]
        for p in self._params:
            if p.grad is not None:
                p._values = [v - lr * g for v, g in zip(p._values, p.grad._values)]


def _make_fake_peft_runtime(*, base_module_names: list[str] | None = None):
    from contextlib import nullcontext

    def _tensor(data, dtype=None, device=None):
        flat: list[float] = []
        for row in data:
            if isinstance(row, (list, tuple)):
                flat.extend(float(x) for x in row)
            else:
                flat.append(float(row))
        return _FakeTensor(flat)

    def _clip_grad_norm(params, max_norm: float):
        sq = sum(g * g for p in params if p.grad is not None for g in p.grad._values)
        norm = sq ** 0.5
        if norm > max_norm > 0:
            ratio = max_norm / norm
            for p in params:
                if p.grad is not None:
                    p.grad._values = [g * ratio for g in p.grad._values]
        return _FakeTensor([norm])

    def _isfinite(tensor: _FakeTensor):
        ok = all(not (v != v or v in (float("inf"), float("-inf"))) for v in tensor._values)
        return SimpleNamespace(all=lambda: SimpleNamespace(item=lambda: ok))

    torch_mod = SimpleNamespace(
        Tensor=_FakeTensor,
        float32="torch.float32",
        float16="torch.float16",
        bfloat16="torch.bfloat16",
        long="torch.long",
        manual_seed=lambda seed: None,
        tensor=_tensor,
        isfinite=_isfinite,
        no_grad=nullcontext,
        nn=SimpleNamespace(utils=SimpleNamespace(clip_grad_norm_=_clip_grad_norm)),
        optim=SimpleNamespace(AdamW=_FakeAdamW),
        cuda=SimpleNamespace(is_available=lambda: False, device_count=lambda: 0),
    )

    def _get_adapter_sd(model: _FakePeftModel):
        return {
            name.replace(".default.", "."): param
            for name, param in model._adapter_params.items()
        }

    def _set_adapter_sd(model: _FakePeftModel, state: dict[str, _FakeTensor]):
        for key, tensor in state.items():
            full_key = key.replace(".weight", ".default.weight")
            assert full_key in model._adapter_params
            model._adapter_params[full_key]._values = list(tensor._values)

    def _load_safetensors(path: str, device: str = "cpu"):
        raw = _read_minimal_f32_safetensors(Path(path))
        return {k: _FakeTensor(vals, shape=shape) for k, (shape, vals) in raw.items()}

    peft_mod = SimpleNamespace(
        LoraConfig=lambda **kw: SimpleNamespace(**kw),
        get_peft_model=lambda base, cfg: _FakePeftModel(base, cfg),
        get_peft_model_state_dict=_get_adapter_sd,
        set_peft_model_state_dict=_set_adapter_sd,
    )
    safetensors_torch_mod = SimpleNamespace(load_file=_load_safetensors)
    tokenizer_cls = SimpleNamespace(from_pretrained=lambda *a, **kw: DeterministicStubTokenizer())
    model_cls = SimpleNamespace(from_pretrained=lambda *a, **kw: _FakeBaseModel(module_names=base_module_names))
    return SimpleNamespace(
        torch=torch_mod,
        peft=peft_mod,
        safetensors_torch=safetensors_torch_mod,
        tokenizer_cls=tokenizer_cls,
        model_cls=model_cls,
    )


def _write_records_json(path: Path, records: list[DataTrainingRecord], manifest_sha: str) -> Path:
    serialized = []
    for rec in records:
        if isinstance(rec.labels, FieldLabels):
            labels_dict = {
                "version": rec.labels.version,
                "fields": [
                    {"pointer": f.pointer, "value": f.value, "status": f.status}
                    for f in rec.labels.fields
                ],
            }
        else:
            from vietdoc.data.adapters.labels import field_labels

            fl = field_labels(rec.gold, rec.labels)
            labels_dict = {
                "version": fl.version,
                "fields": [
                    {"pointer": f.pointer, "value": f.value, "status": f.status}
                    for f in fl.fields
                ],
            }
        serialized.append(
            {
                "sample": {
                    "sample_id": rec.sample_id,
                    "base_id": rec.base_id,
                    "family_id": rec.family_id,
                    "source_group": rec.source_group,
                    "assignment_group": rec.assignment_group,
                    "split": rec.split,
                    "document_type": rec.document_type,
                    "content_sha256": rec.content_sha256,
                    "population_id": rec.population_id,
                    "assets": {"png": {"path": f"{rec.sample_id}.png", "sha256": rec.input_sha256}},
                },
                "gold": rec.gold,
                "labels": labels_dict,
            }
        )
    payload = {
        "artifact_version": "vietdoc.training-records.v1",
        "manifest": {"name": "manifest.json", "version": "d2.synthetic-fixture.v1", "sha256": manifest_sha},
        "records": serialized,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_s02_training_config_splits_from_strict_inference_and_feeds_dataset_collator(tmp_path):
    checked_in = ROOT / "src/vietdoc/ml/configs/qwen-g0.yaml"
    train_yaml = tmp_path / "train-opt-in.yaml"
    text = checked_in.read_text(encoding="utf-8")
    text = text.replace("enabled: false", "enabled: true", 1)
    text = text.replace("allow_training: false", "allow_training: true", 1)
    text = text.replace("dtype: bfloat16", "dtype: float32", 1)
    text = text.replace("device: cuda:0", "device: cpu", 1)
    train_yaml.write_text(text, encoding="utf-8")

    # Strict inference loader MUST still reject allow_training=true.
    with pytest.raises(MLFailure, match="CONFIG_INVALID"):
        load_config(train_yaml, repository_root=ROOT)

    mapping = _make_qwen_config_dict()
    mapping["execution"]["allow_training"] = True
    with pytest.raises(MLFailure, match="CONFIG_INVALID"):
        QwenConfig.from_mapping(mapping, ROOT)

    # Training loader accepts the explicit training YAML and derives a non-executable QwenConfig.
    train_cfg = load_training_config(train_yaml, repository_root=ROOT)
    assert train_cfg.execution_enabled is True
    assert train_cfg.allow_training is True
    assert train_cfg.device == "cpu" and train_cfg.dtype == "float32"
    assert train_cfg.lora.r == 8 and train_cfg.lora.lora_alpha == 16

    derived = train_cfg.to_inference_config()
    assert isinstance(derived, QwenConfig)
    assert derived.execution_enabled is False
    assert derived.schema_sha256 == SCHEMA_SHA256
    assert derived.max_sequence_tokens == 5120
    # Derived config cannot activate QwenLoader inference.
    with pytest.raises(MLFailure, match="EXECUTION_DISABLED"):
        QwenLoader(derived, tmp_path).load()

    # Both derived QwenConfig and G0TrainingConfig feed dataset join and collator cleanly.
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    dataset = join_training_dataset(
        bundle_dir,
        records,
        train_cfg,
        expected_engine_sha256=index["engine_manifest"]["engine_sha256"],
        expected_profile_sha256=index["profile"]["profile_sha256"],
    )
    batch = TrainingCollator(train_cfg, DeterministicStubTokenizer()).collate(dataset.examples)
    assert batch.sample_ids == ("rec_train_01", "inv_train_02")

    # Forbidden flags and non-bool allow_training remain rejected even in the training helper.
    for flag, bad_val in (
        ("allow_download", True),
        ("allow_paid_compute", True),
        ("runtime_activation", True),
        ("allow_training", "true"),
        ("allow_training", 1),
    ):
        bad = deepcopy(mapping)
        bad["execution"][flag] = bad_val
        with pytest.raises(MLFailure, match="CONFIG_INVALID"):
            derive_inference_config_for_training(bad, ROOT)


def test_s03_checked_in_config_remains_blocked_in_peft_entrypoint_and_cli(tmp_path, capsys):
    checked_in = ROOT / "src/vietdoc/ml/configs/qwen-g0.yaml"
    out_root = tmp_path / "runs"
    out_root.mkdir()
    run_dir = out_root / "should-not-exist"
    factory = Mock(side_effect=AssertionError("must not import runtime when disabled"))
    result = run_qwen_lora_g0_training(
        config_path=checked_in,
        snapshot_dir=tmp_path / "snap",
        ocr_bundle_dir=tmp_path / "bundle",
        records_path=tmp_path / "records.json",
        allowed_output_root=out_root,
        output_dir=run_dir,
        evaluator_version="eval.v1",
        evaluator_sha256="e" * 64,
        repository_root=ROOT,
        runtime_factory=factory,
    )
    assert result.status == "G0_NOT_RUN"
    assert result.error_code == "TRAINING_EXECUTION_DISABLED"
    assert result.production_active is False
    assert result.g0_acceptance_claimed is False
    factory.assert_not_called()
    assert not run_dir.exists()

    rc = g0_cli_main(
        [
            "--train",
            "--config",
            str(checked_in),
            "--snapshot",
            str(tmp_path / "snap"),
            "--ocr-bundle",
            str(tmp_path / "bundle"),
            "--records",
            str(tmp_path / "records.json"),
            "--allowed-output-root",
            str(out_root),
            "--output-dir",
            str(run_dir),
            "--evaluator-version",
            "eval.v1",
            "--evaluator-sha256",
            "e" * 64,
            "--repo-root",
            str(ROOT),
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "G0_NOT_RUN"
    assert payload["error_code"] == "TRAINING_EXECUTION_DISABLED"
    assert payload["production_active"] is False
    assert not run_dir.exists()


def test_s03_lora_target_validation_and_missing_peft_dependency(tmp_path, monkeypatch):
    spec = LoRAConfigSpec()
    # Zero matches -> ADAPTER_TARGET_INVALID.
    empty_model = _FakeBaseModel(module_names=["model.layers.0.mlp.up_proj"])
    with pytest.raises(MLFailure, match="ADAPTER_TARGET_INVALID"):
        validate_lora_target_modules(empty_model, spec)

    # Pattern matching embeddings or lm_head -> ADAPTER_TARGET_INVALID.
    bad_spec = LoRAConfigSpec(target_modules=r".*(embed_tokens|q_proj)$")
    with pytest.raises(MLFailure, match="ADAPTER_TARGET_INVALID"):
        validate_lora_target_modules(_FakeBaseModel(), bad_spec)

    # Missing peft dependency returns typed G0_NOT_RUN (never fake PASS).
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    records_path = _write_records_json(tmp_path / "records.json", records, index["source_manifest_sha256"])
    snap_dir = tmp_path / provision.REVISION
    snap_dir.mkdir()
    (snap_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (snap_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    out_root = tmp_path / "runs"
    out_root.mkdir()
    mapping = _make_qwen_config_dict()
    mapping["execution"]["allow_training"] = True
    train_cfg = G0TrainingConfig.from_mapping(mapping, ROOT)

    monkeypatch.setitem(sys.modules, "peft", None)
    result = run_qwen_lora_g0_training(
        config=train_cfg,
        snapshot_dir=snap_dir,
        ocr_bundle_dir=bundle_dir,
        records_path=records_path,
        allowed_output_root=out_root,
        output_dir=out_root / "no-peft",
        evaluator_version="eval.v1",
        evaluator_sha256="e" * 64,
        snapshot_verifier=lambda _p: {"model_id": provision.MODEL_ID, "revision": provision.REVISION},
    )
    assert result.status == "G0_NOT_RUN"
    assert result.error_code == "TRAINING_DEPENDENCY_MISSING"
    assert result.stage == "dependency"
    assert not (out_root / "no-peft").exists()


def test_s03_peft_lora_entrypoint_adapter_only_save_clean_reload_and_tamper_detection(tmp_path):
    bundle_dir, index, records, _ = _build_verified_bundle_and_records(tmp_path)
    dev_ref = DataTrainingRecord(
        sample_id="dev_ref_01",
        base_id="base-dev-01",
        family_id="receipt-fam-dev-99",
        source_group="src-dev-99",
        assignment_group="grp-dev-99",
        split="dev",
        document_type="receipt",
        input_sha256="c" * 64,
        gold=records[0].gold,
        labels=records[0].labels,
        content_sha256="d" * 64,
        population_id="synthetic-pop-v1",
        dataset_manifest_sha256=index["source_manifest_sha256"],
    )
    records_path = _write_records_json(
        tmp_path / "records.json",
        [*records, dev_ref],
        index["source_manifest_sha256"],
    )
    snap_dir = tmp_path / provision.REVISION
    snap_dir.mkdir()
    (snap_dir / "manifest.json").write_text('{"manifest_version":1}', encoding="utf-8")
    (snap_dir / "tokenizer.json").write_text('{"version":"1.0"}', encoding="utf-8")

    out_root = tmp_path / "peft-runs"
    out_root.mkdir()
    run_dir = out_root / "lora-g0-01"
    mapping = _make_qwen_config_dict()
    mapping["execution"]["allow_training"] = True
    mapping["training_g0"]["learning_rate"] = 0.05
    train_cfg = G0TrainingConfig.from_mapping(mapping, ROOT)

    runtime = _make_fake_peft_runtime()
    result = run_qwen_lora_g0_training(
        config=train_cfg,
        snapshot_dir=snap_dir,
        ocr_bundle_dir=bundle_dir,
        records_path=records_path,
        allowed_output_root=out_root,
        output_dir=run_dir,
        evaluator_version="vietdoc.synthetic-eval.v1",
        evaluator_sha256="e" * 64,
        clean_process_verify=True,
        runtime_factory=lambda: runtime,
        snapshot_verifier=lambda _p: {"model_id": provision.MODEL_ID, "revision": provision.REVISION},
        evidence_scope="synthetic_machinery_only",
    )

    assert result.status == "G0_COMPLETED"
    assert result.error_code is None
    assert result.steps_completed == 2
    assert result.parameter_delta_l2 is not None and result.parameter_delta_l2 > 0.0
    assert result.reload_verified is True
    assert result.reload_max_output_diff is not None and result.reload_max_output_diff <= 1e-5
    assert result.production_active is False
    assert result.g0_acceptance_claimed is False

    # Adapter-only files saved; no full base model shards or weights.pt.
    ckpt_dir = run_dir / "checkpoint"
    assert (ckpt_dir / "adapter" / "adapter_config.json").is_file()
    assert (ckpt_dir / "adapter" / "adapter_model.safetensors").is_file()
    assert not (ckpt_dir / "weights.pt").exists()

    verified = verify_checkpoint_in_clean_process(
        run_dir,
        expected_checkpoint_manifest_sha256=result.checkpoint_manifest_sha256,
        expected_run_manifest_sha256=result.run_manifest_sha256,
        expect_adapter_only=True,
    )
    assert verified["adapter_only"] is True
    assert verified["adapter_verified"] is True
    assert verified["adapter_tensor_count"] == 2
    assert verified["parameter_count"] == 8

    # Tampering adapter_model.safetensors must fail closed both in-process and in clean process.
    adapter_file = ckpt_dir / "adapter" / "adapter_model.safetensors"
    orig_bytes = adapter_file.read_bytes()
    tampered = bytearray(orig_bytes)
    tampered[-1] ^= 0xFF
    adapter_file.write_bytes(bytes(tampered))
    with pytest.raises(MLFailure, match="CHECKPOINT_HASH_MISMATCH"):
        verify_checkpoint(run_dir)
    with pytest.raises(MLFailure, match="RELOAD_VERIFICATION_FAILED"):
        verify_checkpoint_in_clean_process(run_dir, expect_adapter_only=True)
    adapter_file.write_bytes(orig_bytes)
    assert verify_checkpoint(run_dir)["adapter_verified"] is True

    # Final split inside records.json must fail closed before loading runtime.
    final_rec = replace(dev_ref, sample_id="final_01", base_id="base-final-01", split="final")
    final_records_path = _write_records_json(
        tmp_path / "records-final.json",
        [*records, final_rec],
        index["source_manifest_sha256"],
    )
    blocked_final = run_qwen_lora_g0_training(
        config=train_cfg,
        snapshot_dir=snap_dir,
        ocr_bundle_dir=bundle_dir,
        records_path=final_records_path,
        allowed_output_root=out_root,
        output_dir=out_root / "lora-final-blocked",
        evaluator_version="vietdoc.synthetic-eval.v1",
        evaluator_sha256="e" * 64,
        runtime_factory=Mock(side_effect=AssertionError("must not load runtime on final split")),
        snapshot_verifier=lambda _p: {"model_id": provision.MODEL_ID, "revision": provision.REVISION},
        evidence_scope="synthetic_machinery_only",
    )
    assert blocked_final.status == "G0_NOT_RUN"
    assert blocked_final.error_code == "FINAL_SPLIT_FORBIDDEN"
    assert not (out_root / "lora-final-blocked").exists()
