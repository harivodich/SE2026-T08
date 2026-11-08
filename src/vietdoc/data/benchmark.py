"""Bounded local D2.1 pipeline benchmark; synthetic QA only, no final split/inference."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from .manifest import encoded, read_json, require, sha
from .generator import d21
from .generator.rendering import FONT
from .generator.values import CONFIG

VERSION = 'data-capacity.v1'
STAGES = ('render', 'validate', 'load', 'evaluate')
BASE_LIMIT = 40


def disk(path):
    files = [p for p in path.rglob('*') if p.is_file()]
    return dict(files=len(files), logical_bytes=sum(p.stat().st_size for p in files),
                allocated_bytes=sum(p.stat().st_blocks * 512 for p in files)
                if hasattr(os.stat_result, 'st_blocks') else None)


def cgroup_limit(name):
    """Best-effort visible cgroup v2 limit, not a GPU/resource feasibility claim."""
    try:
        return (Path('/sys/fs/cgroup') / name).read_text().strip()
    except OSError:
        return None


def workload(rows, base_limit, repeats, timeout):
    require(type(base_limit) is int and 1 <= base_limit <= BASE_LIMIT, 'base-limit must be in [1,40]')
    require(type(repeats) is int and 1 <= repeats <= 3, 'repeats must be in [1,3]')
    require(type(timeout) is int and 1 <= timeout <= 600, 'stage timeout must be in [1,600] seconds')
    require(rows and len(rows) <= 9 and len(set(rows)) == len(rows) and
            all(type(n) is int and 0 <= n <= 30 for n in rows), 'unique rows must be in [0,30], at most 9 profiles')
    # Four type/layout combinations, plus two missing-total and two overflow probes.
    attempts = 4 * len(rows) + 4
    require(attempts <= base_limit, 'requested workload exceeds base-limit (including rejection probes)')
    return attempts


def worker(stage, root, output):
    """Each stage runs once in a fresh process. Imports/setup excluded from timer."""
    from vietdoc.evaluation import extended
    dataset = output / 'dataset'
    manifest_path = dataset / 'manifest.json'
    config = read_json(output / 'config.json')
    workload(config['rows'], config['base_limit'], config['repeats'], config['stage_timeout_seconds'])
    require(type(config['seed']) is int and 0 <= config['seed'] < 2**63, 'seed range')
    expected_config = dict(d21.load_config(d21.DEFAULT_CONFIG), rows=config['rows'])
    require(read_json(output / 'renderer-config.json') == expected_config, 'worker renderer config drift')
    if stage != 'render':
        manifest = read_json(manifest_path)
        require(manifest['version'] == d21.VERSION and manifest['config'] == expected_config and
                manifest['seed'] == config['seed'], 'worker requires bounded D2.1 manifest')
        require(len(manifest['samples']) <= config['attempted_bases_per_repeat'] and
                all(s.get('split') is None for s in manifest['samples']), 'worker forbids split/final inputs')
    samples = artifact = None
    if stage == 'evaluate':
        # Loading/semantic gate has its own measurement; core scoring is timed here.
        _, samples, _, _ = extended.load_bundle(root, manifest_path)
        artifact = dict(artifact_version='vietdoc.predictions.v1',
                        model_version='synthetic-cost-probe.v1', normalizer_version='not-applicable',
                        ocr_version='not-applicable', predictions=[
                            dict(sample_id=s['sample_id'], status='ok', payload=s['gold']) for s in samples])
    start_cpu = time.process_time()
    start = time.perf_counter()
    if stage == 'render':
        manifest = d21.build(root, dataset, seed=config['seed'], config_path=output / 'renderer-config.json')
        result = dict(accepted=len(manifest['samples']), rejections=read_json(dataset / 'rejections.json'))
    elif stage == 'validate':
        result = d21.validate(root, manifest_path)
    elif stage == 'load':
        _, samples, pins, validation = extended.load_bundle(root, manifest_path)
        result = dict(samples=len(samples), asset_pins=len(pins), validation=validation['status'])
    else:
        result = extended.evaluate(samples, artifact)
    elapsed = time.perf_counter() - start
    cpu = time.process_time() - start_cpu
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    measurement = dict(stage=stage, status='ok', wall_seconds=elapsed, cpu_seconds=cpu,
                       process_peak_rss_bytes=peak if sys.platform == 'darwin' else peak * 1024,
                       disk=disk(output), result=result)
    (output / f'{stage}.json').write_bytes(encoded(measurement))


def run(root, output, rows=(1,), base_limit=40, repeats=1, timeout=300, seed=2101):
    attempts = workload(rows, base_limit, repeats, timeout)
    require(type(seed) is int and 0 <= seed < 2**63, 'seed range')
    renderer_config = dict(d21.load_config(d21.DEFAULT_CONFIG), rows=list(rows))
    require(sha(FONT) == renderer_config['font_sha256'], 'font differs from pinned Data environment')
    source_root = Path(__file__).resolve().parents[1]
    sources = {p.relative_to(source_root).as_posix(): sha(p)
               for folder in ('data', 'evaluation') for p in sorted((source_root / folder).rglob('*.py'))}
    cpuinfo = Path('/proc/cpuinfo')
    cpu_model = next((line.split(':', 1)[1].strip() for line in cpuinfo.read_text().splitlines()
                      if line.startswith('model name')), None) if cpuinfo.exists() else platform.processor()
    config = dict(rows=list(rows), base_limit=base_limit, repeats=repeats, seed=seed,
                  stage_timeout_seconds=timeout, attempted_bases_per_repeat=attempts,
                  total_attempted_bases=attempts * repeats, renderer_config=renderer_config)
    report = dict(version=VERSION, status='running', started_utc=datetime.now(timezone.utc).isoformat(),
                  config=config, generator_version=d21.VERSION, dataset_scope='synthetic integration/boundary QA; no split',
                  config_sha256=hashlib.sha256(encoded(config)).hexdigest(),
                  renderer_default_config_sha256=sha(d21.DEFAULT_CONFIG),
                  source_sha256=sources, schema_sha256=sha(root / 'specs/contracts/business.schema.json'),
                  vocabulary_sha256=sha(CONFIG), environment=d21.environment(),
                  hardware=dict(cpu_model=cpu_model, logical_cpus=os.cpu_count(), machine=platform.machine(),
                                os=platform.platform(), physical_memory_bytes=os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')),
                  measurement_scope=dict(render='D2.1 build: values, render, encode, write and rejection probes',
                                         validate='strict D2.1 replay including re-render and byte comparison',
                                         load='D3.2 load_bundle including semantic gate and asset hashing',
                                         evaluate='D3.2 core scalar/table/evidence with gold-copy synthetic payload; OCR absent',
                                         memory='process lifetime peak RSS including imports and setup; not stage delta',
                                         cache='OS caches uncontrolled; each stage in a fresh process; no warmup',
                                         disk='recursive file sizes, before own stage result write; allocated bytes filesystem dependent'),
                  limitations=['No OCR/model/training/GPU measurement or quality claim',
                               'No D2.2 augmentation, family split or duplicate scan measurement',
                               'No final holdout input; no arbitrary input/config/model path accepted',
                               'AI2 hardware/model feasibility and Lead final budget remain pending'], runs=[])
    report['hardware'].update(cpu_affinity_count=len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
                              visible_cgroup_v2_memory_max=cgroup_limit('memory.max'),
                              visible_cgroup_v2_cpu_max=cgroup_limit('cpu.max'))
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / 'benchmark.json'
    report_path.write_bytes(encoded(report))
    try:
        for index in range(repeats):
            trial = output / f'run-{index + 1:02}'
            trial.mkdir()
            (trial / 'config.json').write_bytes(encoded(config))
            (trial / 'renderer-config.json').write_bytes(encoded(renderer_config))
            observation = dict(index=index + 1, stages=[])
            report['runs'].append(observation)
            for stage in STAGES:
                command = [sys.executable, '-m', __spec__.name, '--worker', stage,
                           '--root', str(root), '--output', str(trial)]
                subprocess.run(command, check=True, timeout=timeout, capture_output=True, text=True)
                measurement = read_json(trial / f'{stage}.json')
                # Keep full evaluation details separately, not duplicated in summary.
                measurement.pop('result')
                observation['stages'].append(measurement)
                report_path.write_bytes(encoded(report))
            manifest = read_json(trial / 'dataset/manifest.json')
            observation.update(manifest_sha256=sha(trial / 'dataset/manifest.json'),
                               accepted=len(manifest['samples']),
                               by_type=dict(Counter(s['document_type'] for s in manifest['samples'])),
                               rejections=read_json(trial / 'dataset/rejections.json'), dataset_disk=disk(trial / 'dataset'))
        report['status'] = 'complete'
    except (subprocess.SubprocessError, OSError, ValueError) as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            report['worker_stderr'] = error.stderr
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['output_disk_before_summary_write'] = disk(output)
        report_path.write_bytes(encoded(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rows', type=int, nargs='+', default=[1])
    parser.add_argument('--base-limit', type=int, default=40)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--stage-timeout', type=int, default=300)
    parser.add_argument('--seed', type=int, default=2101)
    parser.add_argument('--worker', choices=STAGES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.worker:
            worker(args.worker, args.root.resolve(), args.output.resolve())
        else:
            report = run(args.root.resolve(), args.output.resolve(), args.rows, args.base_limit,
                         args.repeats, args.stage_timeout, args.seed)
            print(encoded(dict(status=report['status'], report=str(args.output.resolve() / 'benchmark.json'))).decode(), end='')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Benchmark failed: {error}\n')


if __name__ == '__main__':
    main()
