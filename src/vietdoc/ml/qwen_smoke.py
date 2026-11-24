"""Explicit offline OCR-to-Qwen smoke. No download, training, HTTP activation or gold input."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

from vietdoc.ml.model_loading import QwenLoader
from vietdoc.ml.qwen_config import MLFailure, load_config
from vietdoc.ml.qwen_inference import QwenInference


def _read(path):
    def unique(pairs):
        data = {}
        for key,value in pairs:
            if key in data:
                raise ValueError()
            data[key] = value
        return data
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError()
        return json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError,ValueError,RecursionError):
        raise MLFailure('INPUT_FILE_INVALID','input') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config','snapshot','ocr','prepared','provenance','output-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--type',dest='document_type',choices=('receipt','invoice'),required=True)
    parser.add_argument('--timeout-seconds',type=float,default=60)
    parser.add_argument('--repeat',type=int,default=2,help='1..10 sequential generations; retain first and subsequent timings')
    args = parser.parse_args(argv)
    loader = None
    try:
        if (not math.isfinite(args.timeout_seconds) or not 0<args.timeout_seconds<=300
                or not 1<=args.repeat<=10):
            raise MLFailure('DEADLINE_INVALID','input')
        config = load_config(args.config)
        # The checked-in config is deliberately disabled. Only a reviewed local
        # config copy may enable execution; the CLI never modifies that decision.
        if not config.execution_enabled:
            raise MLFailure('EXECUTION_DISABLED','load')
        page,prepared,source = (_read(p) for p in (args.ocr,args.prepared,args.provenance))
        if args.output_dir.exists():
            raise MLFailure('OUTPUT_EXISTS','export')
        loader = QwenLoader(config,args.snapshot)
        loader.load()
        adapter = QwenInference(loader)
        runs = []
        for _ in range(args.repeat):
            result = adapter.run(page,prepared,source,args.document_type,
                                 deadline=time.monotonic()+args.timeout_seconds)
            runs.append(asdict(result))
            if result.error:
                break
        report = asdict(result)
        report.update(document_type=args.document_type,model_id=config.model_id,
            revision=config.revision,config_sha256=config.config_sha256,
            native_inference_attempted=loader.generation_attempts>0,
            generation_attempts=loader.generation_attempts,production_active=False,load_metrics=loader.load_metrics,
            generations=runs,warm_generation_seconds=[r['seconds'] for r in runs[1:]])
        # Serialize before creating files. Caller must choose ignored, owner-controlled
        # storage; raw output is private and intentionally never printed to stdout.
        encoded = (json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8')
        args.output_dir.mkdir(parents=True,exist_ok=False)
        with (args.output_dir/'report.json').open('xb') as stream:
            stream.write(encoded)
        print(json.dumps({'error':result.error,'stage':result.stage,
                          'native_inference_attempted':loader.generation_attempts>0,'production_active':False}))
        return 0 if result.error is None else 1
    except MLFailure as error:
        print(json.dumps({'error':error.code,'stage':error.stage,'production_active':False,
                          'native_inference_attempted':loader is not None and loader.generation_attempts>0}))
        return 2 if error.code in ('EXECUTION_DISABLED','MODEL_NOT_VERIFIED','CONFIG_DEPENDENCY_MISSING') else 1
    except (OSError,ValueError,TypeError):
        print(json.dumps({'error':'SMOKE_IO_FAILED','stage':'export','production_active':False}))
        return 1
    finally:
        if loader is not None:
            loader.close()


if __name__=='__main__':
    raise SystemExit(main())
