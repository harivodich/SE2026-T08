"""Regression checks for S-04 isolated ai-train runtime pins and RTX 3060 compose defaults."""

from __future__ import annotations

from pathlib import Path
import tomllib

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_s04_pyproject_train_extra_includes_pinned_pyyaml_without_weakening_other_extras():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    train = extras["train"]
    test = extras["test"]

    assert "PyYAML==6.0.3" in train
    assert "PyYAML==6.0.3" in test
    # Preserve existing core pins and Data isolation.
    assert "peft==0.21.2" in train
    assert "transformers==5.20.2" in train
    assert "safetensors==0.8.0" in train
    assert extras["data"] == ["Pillow==10.2.0", "jsonschema==4.10.3"]


def test_s04_ai_train_dockerfile_verifies_pyyaml_and_preserves_offline_hardening():
    dockerfile = (ROOT / "infra/ai-train.Dockerfile").read_text(encoding="utf-8")
    assert 'pip install ".[train]"' in dockerfile
    assert "m.version('PyYAML') == '6.0.3'" in dockerfile
    assert "HF_HUB_OFFLINE=1" in dockerfile
    assert "TRANSFORMERS_OFFLINE=1" in dockerfile
    assert "HF_HUB_DISABLE_IMPLICIT_TOKEN=1" in dockerfile
    assert "USER app" in dockerfile
    assert 'CMD ["python", "-m", "vietdoc.entrypoints.cli.env_report"]' in dockerfile


def test_s04_compose_ai_train_has_safe_rtx3060_memory_defaults_and_remains_offline():
    compose = yaml.safe_load((ROOT / "infra/compose.ai.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    train = services["ai-train"]
    train_gpu = services["ai-train-gpu"]

    for svc_name, svc in (("ai-train", train), ("ai-train-gpu", train_gpu)):
        assert svc["network_mode"] == "none", f"{svc_name} must remain offline"
        assert svc["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in svc["security_opt"]
        env = svc["environment"]
        assert env["HF_HUB_OFFLINE"] == "1"
        assert env["TRANSFORMERS_OFFLINE"] == "1"
        assert env["HF_HUB_DISABLE_IMPLICIT_TOKEN"] == "1"
        assert env["VIETDOC_CHECKPOINTS_DIR"] == "/checkpoints"
        # Safe default above 8g for Qwen3-1.7B host load + RTX 3060 12GB buffers, fitting 16GB+ hosts.
        assert svc["mem_limit"] == "${AI_TRAIN_MEMORY:-12g}"

    assert train["profiles"] == ["train"]
    assert train_gpu["profiles"] == ["gpu"]
    assert train_gpu["gpus"] == "all"
    alloc_conf = train_gpu["environment"]["PYTORCH_CUDA_ALLOC_CONF"]
    assert "expandable_segments:True" in alloc_conf
    assert "max_split_size_mb:128" in alloc_conf
    assert train_gpu["shm_size"] == "${AI_TRAIN_SHM_SIZE:-2g}"

    # Ensure serving service offline/security defaults were not weakened.
    serve = services["ai-service"]
    assert serve["read_only"] is True
    assert serve["environment"]["HF_HUB_OFFLINE"] == "1"
    assert serve["environment"]["TRANSFORMERS_OFFLINE"] == "1"
