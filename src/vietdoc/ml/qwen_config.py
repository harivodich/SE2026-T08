"""Validated offline inference settings. No model frameworks or implicit execution."""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from vietdoc.ml import model_provision

EXPECTED_SCHEMA_PATH = 'specs/contracts/business.schema.json'
FORBIDDEN_EXECUTION_FLAGS = ('allow_download', 'allow_training', 'allow_paid_compute')
LEGACY_SERIALIZATION = 'vietdoc_ocr_context_v1'
COMPACT_SERIALIZATION = 'vietdoc_ocr_context_v2'


class MLFailure(ValueError):
    """Internal AI-2 typed failure; codes are not new shared HTTP enums."""
    def __init__(self, code: str, stage: str):
        self.code, self.stage = code, stage
        super().__init__(code)


def _validated_schema_path(repository_root: Path, schema_path: object) -> Path:
    if schema_path != EXPECTED_SCHEMA_PATH or not isinstance(repository_root, (str, os.PathLike)):
        raise ValueError()
    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError()
    current = root
    for part in ('specs', 'contracts', 'business.schema.json'):
        current = current / part
        st = current.lstat()
        if (current.is_symlink() or stat.S_ISLNK(st.st_mode)
                or getattr(st, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise ValueError()
    if not stat.S_ISREG(st.st_mode) or st.st_size > 1024 * 1024:
        raise ValueError()
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved != root / 'specs' / 'contracts' / 'business.schema.json':
        raise ValueError()
    return resolved


@dataclass(frozen=True)
class QwenConfig:
    model_id: str
    revision: str
    schema_path: Path
    schema_sha256: str
    max_input_tokens: int
    max_ocr_tokens: int
    max_new_tokens: int
    max_sequence_tokens: int
    device: str
    dtype: str
    execution_enabled: bool
    config_sha256: str
    serialization_version: str = LEGACY_SERIALIZATION

    @classmethod
    def from_mapping(cls, data, repository_root: Path):
        try:
            if not isinstance(data, dict):
                raise ValueError()
            model, inp, out, infer, execution, profiles = (
                data[k] for k in ('model','input','output','inference','execution','profiles'))
            if any(not isinstance(s, dict) for s in (model, inp, out, infer, execution, profiles)):
                raise ValueError()
            selected = infer['selected_profile']
            if not isinstance(selected, str):
                raise ValueError()
            profile = profiles[selected]
            if not isinstance(profile, dict):
                raise ValueError()
            if (model['id'] != model_provision.MODEL_ID or model['revision'] != model_provision.REVISION
                    or model['tokenizer_revision'] != model['revision']
                    or model['local_files_only'] is not True or model['trust_remote_code'] is not False
                    or model['use_safetensors'] is not True
                    or inp['input_profile'] != 'ocr_text_layout_v1'
                    or infer['input_profile'] != inp['input_profile'] or inp['accept_image_input'] is not False
                    or infer['enable_thinking'] is not False or infer['do_sample'] is not False
                    or type(infer['num_beams']) is not int or infer['num_beams'] != 1
                    or type(infer['batch_size']) is not int or infer['batch_size'] != 1
                    or profile.get('quantization', 'none') != 'none' or profile.get('load_in_4bit', False)):
                raise ValueError()
            budgets = (inp['max_input_tokens'], inp['ocr_context']['max_tokens_when_enabled'],
                       infer['max_new_tokens'], infer['max_sequence_tokens'])
            if (any(type(n) is not int or n <= 0 or n > 40960 for n in budgets)
                    or budgets[1] > budgets[0] or budgets[0] + budgets[2] > budgets[3]):
                raise ValueError()
            serialization = inp['ocr_context'].get('serialization_version', LEGACY_SERIALIZATION)
            if serialization not in (LEGACY_SERIALIZATION, COMPACT_SERIALIZATION):
                raise ValueError()
            device, dtype = profile['device'], profile['dtype']
            if (not isinstance(device,str) or not re.fullmatch(r'cpu|cuda:(?:0|[1-9][0-9]{0,5})',device)
                    or dtype not in ('float32','float16','bfloat16')
                    or device == 'cpu' and dtype != 'float32'):
                raise ValueError()
            enabled = execution['enabled']
            if (type(enabled) is not bool or execution['runtime_activation'] is not False
                    or any(execution.get(flag, False) is not False for flag in FORBIDDEN_EXECUTION_FLAGS)
                    or not isinstance(out['schema_sha256'], str)):
                raise ValueError()
            schema = _validated_schema_path(repository_root, out['schema_path'])
            digest = hashlib.sha256(schema.read_bytes()).hexdigest()
            if digest != out['schema_sha256']:
                raise MLFailure('SCHEMA_HASH_MISMATCH','config')
            fingerprint = hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False,
                ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
            return cls(model['id'],model['revision'],schema,digest,*budgets,device,dtype,enabled,fingerprint,
                       serialization)
        except MLFailure:
            raise
        except (KeyError,TypeError,ValueError,OSError):
            raise MLFailure('CONFIG_INVALID','config') from None


def derive_inference_config_for_training(data: Mapping[str, Any], repository_root: Path) -> QwenConfig:
    """Derive a non-executable inference QwenConfig from a training mapping.

    Allows explicit ``execution.allow_training`` booleans in the training mapping
    while keeping ``QwenConfig.from_mapping`` and ``load_config`` strict for
    inference.  The derived ``QwenConfig`` always has ``execution_enabled=False``
    so it can feed prompt/tokenizer/collator parity without enabling QwenLoader.
    """
    if not isinstance(data, Mapping):
        raise MLFailure('CONFIG_INVALID', 'config')
    execution = data.get('execution')
    if not isinstance(execution, Mapping):
        raise MLFailure('CONFIG_INVALID', 'config')
    enabled = execution.get('enabled')
    allow_training = execution.get('allow_training', False)
    if type(enabled) is not bool or type(allow_training) is not bool:
        raise MLFailure('CONFIG_INVALID', 'config')
    sanitized_execution = dict(execution)
    sanitized_execution['enabled'] = False
    sanitized_execution['allow_training'] = False
    sanitized = dict(data)
    sanitized['execution'] = sanitized_execution
    return QwenConfig.from_mapping(sanitized, repository_root)


def read_config_mapping(path: Path, repository_root: Path | None = None) -> tuple[dict[str, Any], Path]:
    """Optional PyYAML reader with unique-key enforcement and repository root resolution."""
    try:
        import yaml
    except ImportError:
        raise MLFailure('CONFIG_DEPENDENCY_MISSING','config') from None
    path = Path(path)
    try:
        with path.open('rb') as stream:
            raw = stream.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError()
        # safe_load rejects executable tags. Duplicate YAML keys must also fail closed.
        class UniqueLoader(yaml.SafeLoader):
            pass
        def mapping(loader, node):
            pairs = loader.construct_pairs(node, deep=True)
            result = {}
            for key,value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
        data = yaml.load(raw.decode('utf-8'),Loader=UniqueLoader)
        if not isinstance(data, dict):
            raise ValueError()
        if repository_root is None:
            repository_root = next((p for p in Path(__file__).resolve().parents if (p/'specs/contracts').is_dir()), None)
        if repository_root is None:
            contracts_root = os.environ.get('VIETDOC_CONTRACTS_DIR')
            if contracts_root:
                candidate = Path(contracts_root).resolve()
                if candidate.name == 'contracts' and candidate.parent.name == 'specs':
                    repository_root = candidate.parent.parent
        if repository_root is None:
            raise ValueError()
        return data, Path(repository_root)
    except MLFailure:
        raise
    except Exception:
        raise MLFailure('CONFIG_INVALID','config') from None


def load_config(path: Path, repository_root: Path | None = None) -> QwenConfig:
    """Optional PyYAML reader for inference; strictly rejects allow_training=true."""
    data, resolved_root = read_config_mapping(path, repository_root)
    return QwenConfig.from_mapping(data, resolved_root)
