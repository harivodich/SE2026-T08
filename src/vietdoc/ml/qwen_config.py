"""Validated offline inference settings. No model frameworks or implicit execution."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from vietdoc.ml import model_provision


class MLFailure(ValueError):
    """Internal AI-2 typed failure; codes are not new shared HTTP enums."""
    def __init__(self, code: str, stage: str):
        self.code, self.stage = code, stage
        super().__init__(code)


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

    @classmethod
    def from_mapping(cls, data, repository_root: Path):
        try:
            model, inp, out, infer = (data[k] for k in ('model','input','output','inference'))
            profile = data['profiles'][infer['selected_profile']]
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
            device, dtype = profile['device'], profile['dtype']
            if (not isinstance(device,str) or not re.fullmatch(r'cpu|cuda:[0-9]+',device)
                    or dtype not in ('float32','float16','bfloat16')
                    or device == 'cpu' and dtype != 'float32'):
                raise ValueError()
            enabled = data['execution']['enabled']
            if type(enabled) is not bool or data['execution']['runtime_activation'] is not False:
                raise ValueError()
            schema = Path(repository_root) / out['schema_path']
            digest = hashlib.sha256(schema.read_bytes()).hexdigest()
            if digest != out['schema_sha256']:
                raise MLFailure('SCHEMA_HASH_MISMATCH','config')
            fingerprint = hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False,
                ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
            return cls(model['id'],model['revision'],schema,digest,*budgets,device,dtype,enabled,fingerprint)
        except MLFailure:
            raise
        except (KeyError,TypeError,ValueError,OSError):
            raise MLFailure('CONFIG_INVALID','config') from None


def load_config(path: Path, repository_root: Path | None = None) -> QwenConfig:
    """Optional PyYAML reader; callers can use from_mapping without this dependency."""
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
        if repository_root is None:
            repository_root = next(p for p in path.absolute().parents if (p/'specs/contracts').is_dir())
        return QwenConfig.from_mapping(data,repository_root)
    except MLFailure:
        raise
    except Exception:
        raise MLFailure('CONFIG_INVALID','config') from None
