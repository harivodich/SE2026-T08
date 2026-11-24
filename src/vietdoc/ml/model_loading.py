"""Explicit local verified Qwen lifecycle; never downloads or activates serving."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from vietdoc.ml import model_provision
from vietdoc.ml.ocr_adapter import build_prompt
from vietdoc.ml.qwen_config import MLFailure, QwenConfig


@dataclass(frozen=True)
class Generation:
    raw: str
    finish_reason: str
    input_tokens: int
    output_tokens: int
    seconds: float
    provenance: dict


def _runtime():
    # No import at module import time, and only after verified local model preflight.
    import torch
    import transformers
    return SimpleNamespace(torch=torch, tokenizer=transformers.AutoTokenizer,
        model=transformers.AutoModelForCausalLM, stopping_list=transformers.StoppingCriteriaList,
        generation_config=transformers.GenerationConfig,
        versions={'torch':torch.__version__,'transformers':transformers.__version__})


def _host_memory():
    """Available host RAM is best effort, not a container allocation guarantee."""
    try:
        # MemFree excludes reclaimable cache and falsely rejects a verified model
        # immediately after hashing its files. Linux MemAvailable is the usable estimate.
        for line in Path('/proc/meminfo').read_text().splitlines():
            fields = line.split()
            if len(fields)==3 and fields[0]=='MemAvailable:' and fields[2]=='kB':
                return int(fields[1])*1024
    except (OSError,ValueError):
        pass
    try:
        return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (ValueError,AttributeError,OSError):
        return None


def _error(error, stage, oom_type=MemoryError):
    if isinstance(error, MLFailure):
        return error
    if isinstance(error, (MemoryError,oom_type)):
        return MLFailure('OOM',stage)
    if isinstance(error, TimeoutError):
        return MLFailure('TIMEOUT',stage)
    return MLFailure('MODEL_LOAD_FAILED' if stage=='load' else 'GENERATION_FAILED',stage)


def _deadline(deadline):
    if type(deadline) not in (int,float) or not math.isfinite(deadline):
        raise MLFailure('DEADLINE_INVALID','generation')
    if time.monotonic() >= deadline:
        raise MLFailure('TIMEOUT','generation')


def _parse_eos_token_ids(gen_cfg, vocab_size: int) -> tuple[int, ...]:
    if not isinstance(gen_cfg, dict) or 'eos_token_id' not in gen_cfg:
        raise MLFailure('TOKENIZER_INCOMPATIBLE', 'load')
    raw = gen_cfg['eos_token_id']
    if type(raw) is int:
        values = [raw]
    elif isinstance(raw, list) and raw:
        values = raw
    else:
        raise MLFailure('TOKENIZER_INCOMPATIBLE', 'load')
    if any(type(i) is not int or not 0 <= i < vocab_size for i in values):
        raise MLFailure('TOKENIZER_INCOMPATIBLE', 'load')
    return tuple(dict.fromkeys(values))


class QwenLoader:
    """One model instance, single capacity slot; close/load/generate cannot overlap.

    Snapshot storage must be owner-controlled and mounted read-only. Load hashes
    authenticate bytes against recorded upstream metadata, not against a hostile
    owner changing manifests and bytes together. Timeout is cooperative at token
    boundaries; a blocking GPU kernel cannot be interrupted immediately.
    """
    def __init__(self, config: QwenConfig, snapshot: Path, *, runtime_factory=None):
        self.config, self.snapshot = config, Path(snapshot).absolute()
        self._factory = runtime_factory or _runtime
        self._lock = threading.Lock()
        self.model = self.tokenizer = self.runtime = None
        self.eos_token_ids = ()
        self.state = 'unloaded'
        self.load_metrics = {}
        self.provenance = {}
        self.generation_attempts = 0

    @property
    def ready(self):
        return self.state == 'ready'

    def ready_reasons(self):
        if not self.ready:
            return ['MODEL_NOT_READY']
        return ['MODEL_BUSY'] if self._lock.locked() else []

    @contextmanager
    def _slot(self):
        if not self._lock.acquire(blocking=False):
            raise MLFailure('MODEL_BUSY','lifecycle')
        try:
            yield
        finally:
            self._lock.release()

    def load(self):
        with self._slot():
            if self.ready:
                return
            if not self.config.execution_enabled:
                raise MLFailure('EXECUTION_DISABLED','load')
            started = time.monotonic()
            self.state = 'loading'
            self.eos_token_ids = ()
            self.load_metrics = {}
            self.provenance = {}
            try:
                try:
                    verified = model_provision.verify_snapshot(self.snapshot)
                    if verified['revision'] != self.config.revision or verified['model_id'] != self.config.model_id:
                        raise ValueError()
                except Exception:
                    raise MLFailure('MODEL_NOT_VERIFIED','load') from None
                local = json.loads((self.snapshot/'config.json').read_text(encoding='utf-8'))
                if (local.get('model_type')!='qwen3' or local.get('architectures')!=['Qwen3ForCausalLM']
                        or type(local.get('vocab_size')) is not int or local['vocab_size'] <= 0
                        or type(local.get('max_position_embeddings')) is not int
                        or self.config.max_sequence_tokens > local['max_position_embeddings']):
                    raise MLFailure('MODEL_INCOMPATIBLE','load')
                gen_cfg = json.loads((self.snapshot/'generation_config.json').read_text(encoding='utf-8'))
                eos_ids = _parse_eos_token_ids(gen_cfg, local['vocab_size'])
                index = json.loads((self.snapshot/'model.safetensors.index.json').read_text(encoding='utf-8'))
                weight_bytes = index['metadata']['total_size']
                host_free = _host_memory()
                # CPU float32 needs twice the stored BF16 weight bytes, before activations.
                lower_bound = weight_bytes * (2 if self.config.dtype=='float32' else 1)
                if host_free is not None and host_free < lower_bound:
                    raise MLFailure('MEMORY_INSUFFICIENT','load')
                self.runtime = self._factory()
                rt, device = self.runtime, self.config.device
                gpu_free = None
                if device.startswith('cuda:'):
                    ordinal = int(device.split(':')[1])
                    if not rt.torch.cuda.is_available() or ordinal >= rt.torch.cuda.device_count():
                        raise MLFailure('DEVICE_UNAVAILABLE','load')
                    with rt.torch.cuda.device(device):
                        if (self.config.dtype=='bfloat16'
                                and not rt.torch.cuda.is_bf16_supported(including_emulation=False)):
                            raise MLFailure('DTYPE_UNSUPPORTED','load')
                        gpu_free,_ = rt.torch.cuda.mem_get_info()
                    if gpu_free < lower_bound:
                        raise MLFailure('MEMORY_INSUFFICIENT','load')
                kw = dict(local_files_only=True,trust_remote_code=False,revision=self.config.revision)
                self.tokenizer = rt.tokenizer.from_pretrained(str(self.snapshot),**kw)
                if (not isinstance(self.tokenizer.chat_template,str) or not self.tokenizer.chat_template
                        or type(self.tokenizer.eos_token_id) is not int
                        or type(self.tokenizer.pad_token_id) is not int
                        or not 0 < len(self.tokenizer) <= local['vocab_size']):
                    raise MLFailure('TOKENIZER_INCOMPATIBLE','load')
                vocab = self.tokenizer.get_vocab()
                if (not isinstance(vocab,dict) or len(vocab)!=len(self.tokenizer)
                        or any(type(i) is not int or not 0<=i<local['vocab_size'] for i in vocab.values())):
                    raise MLFailure('TOKENIZER_INCOMPATIBLE','load')
                vocab_ids = set(vocab.values())
                if (self.tokenizer.eos_token_id not in vocab_ids
                        or self.tokenizer.pad_token_id not in vocab_ids
                        or self.tokenizer.eos_token_id not in eos_ids
                        or any(i not in vocab_ids for i in eos_ids)
                        or ('pad_token_id' in gen_cfg
                            and (type(gen_cfg['pad_token_id']) is not int
                                 or gen_cfg['pad_token_id'] != self.tokenizer.pad_token_id))):
                    raise MLFailure('TOKENIZER_INCOMPATIBLE','load')
                declared = json.loads((self.snapshot/'tokenizer_config.json').read_text(encoding='utf-8'))
                if self.tokenizer.chat_template != declared.get('chat_template'):
                    raise MLFailure('TOKENIZER_INCOMPATIBLE','load')
                self.model = rt.model.from_pretrained(str(self.snapshot),**kw,use_safetensors=True,
                    torch_dtype=getattr(rt.torch,self.config.dtype),attn_implementation='sdpa')
                eos = self.model.config.eos_token_id
                eos = eos if isinstance(eos,list) else [eos]
                if (self.model.config.model_type!='qwen3'
                        or self.model.get_input_embeddings().num_embeddings != local['vocab_size']
                        or any(type(i) is not int for i in eos)
                        or self.tokenizer.eos_token_id not in eos):
                    raise MLFailure('TOKENIZER_INCOMPATIBLE','load')
                self.model.to(device)
                self.model.eval()
                if self.model.dtype != getattr(rt.torch,self.config.dtype) or str(self.model.device) != device:
                    raise MLFailure('MODEL_INCOMPATIBLE','load')
                self.load_metrics = dict(cold_load_seconds=time.monotonic()-started,
                    available_host_ram_bytes=host_free,available_gpu_bytes=gpu_free,
                    **self._memory())
                self.provenance = dict(model_id=self.config.model_id,revision=self.config.revision,
                    config_sha256=self.config.config_sha256,schema_sha256=self.config.schema_sha256,
                    model_manifest_sha256=hashlib.sha256((self.snapshot/'manifest.json').read_bytes()).hexdigest(),
                    inventory_sha256=hashlib.sha256((self.snapshot/'inventory.json').read_bytes()).hexdigest(),
                    versions=dict(rt.versions),device=device,dtype=self.config.dtype)
                self.eos_token_ids = eos_ids
                self.state = 'ready'
            except Exception as error:
                oom_type = getattr(getattr(self.runtime,'torch',None),'OutOfMemoryError',MemoryError)
                self._release()
                self.state = 'failed'
                raise _error(error,'load',oom_type) from None

    def _memory(self):
        rss = None
        try:
            # Linux resident memory; no package install or fabricated Windows equivalent.
            fields = Path('/proc/self/statm').read_text().split()
            rss = int(fields[1])*os.sysconf('SC_PAGE_SIZE')
        except (OSError,ValueError,AttributeError):
            pass
        vram = peak = None
        if self.runtime is not None and self.config.device.startswith('cuda:'):
            vram = self.runtime.torch.cuda.memory_allocated(self.config.device)
            peak = self.runtime.torch.cuda.max_memory_allocated(self.config.device)
        return dict(rss_bytes=rss,vram_allocated_bytes=vram,process_peak_vram_bytes=peak)

    def _release(self):
        self.model = self.tokenizer = None
        self.eos_token_ids = ()
        self.provenance = {}
        # Do not empty a shared process CUDA cache or promise immediate GPU release.
        self.runtime = None

    def close(self):
        with self._slot():
            self._release()
            self.state = 'closed'

    def generate(self,page,prepared,provenance,document_type,*,deadline):
        with self._slot():
            if not self.ready:
                raise MLFailure('MODEL_NOT_READY','generation')
            _deadline(deadline)
            prompt = build_prompt(page,prepared,provenance,document_type,self.config,self.tokenizer)
            _deadline(deadline)
            rt = self.runtime
            started = time.monotonic()
            class DeadlineStop:
                def __call__(self, input_ids, scores, **kwargs):
                    return time.monotonic() >= deadline
            try:
                ids = rt.torch.tensor([prompt.input_ids],dtype=rt.torch.long,device=self.config.device)
                mask = rt.torch.ones_like(ids)
                # A fresh config avoids model defaults enabling sampling, forced tokens or extra output.
                generation_config = rt.generation_config(do_sample=False,num_beams=1,
                    max_new_tokens=self.config.max_new_tokens,use_cache=True,
                    eos_token_id=list(self.eos_token_ids),pad_token_id=self.tokenizer.pad_token_id,
                    return_dict_in_generate=False)
                with rt.torch.inference_mode():
                    self.generation_attempts += 1
                    output = self.model.generate(input_ids=ids,attention_mask=mask,
                        generation_config=generation_config,stopping_criteria=rt.stopping_list([DeadlineStop()]))
                _deadline(deadline)
                tokens = output[0].tolist()
                _deadline(deadline)
                prefix = list(prompt.input_ids)
                if tokens[:len(prefix)] != prefix:
                    raise MLFailure('MODEL_OUTPUT_INVALID','generation')
                new = tokens[len(prefix):]
                count = len(new)
                # No EOS implies length/cooperative stop; never infer successful completion from JSON alone.
                finish = 'stop' if new and new[-1] in self.eos_token_ids else 'length'
                if count > self.config.max_new_tokens or not new:
                    raise MLFailure('MODEL_OUTPUT_INVALID','generation')
                text = self.tokenizer.decode(new[:-1] if finish=='stop' else new,
                                            skip_special_tokens=False,clean_up_tokenization_spaces=False)
                _deadline(deadline)
                source = dict(self.provenance,ocr=prompt.provenance,diagnostics=list(prompt.diagnostics),
                    ocr_tokens=prompt.ocr_tokens,metrics=self._memory(),load_metrics=dict(self.load_metrics),
                    prompt_sha256=hashlib.sha256(json.dumps(prompt.messages,ensure_ascii=True,
                        sort_keys=True,separators=(',',':')).encode()).hexdigest())
                return Generation(text,finish,len(prefix),count,time.monotonic()-started,source)
            except Exception as error:
                oom_type = getattr(rt.torch,'OutOfMemoryError',MemoryError)
                failure = _error(error,'generation',oom_type)
                if failure.code in ('OOM','GENERATION_FAILED','MODEL_OUTPUT_INVALID'):
                    self._release()
                    self.state = 'failed'
                raise failure from None
