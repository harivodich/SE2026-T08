"""D3.2 offline comparison, traceable correctness export and freeze preparation."""
from collections import Counter, defaultdict
import hashlib
import json
import struct
import re
from pathlib import Path

from vietdoc.data.manifest import asset_path, read_json, require, sha
from . import scalar_ocr
from .policy import FIELDS, VERSION as NORMALIZATION_VERSION
from .tables import POLICY, cell, evaluate_table, table_metrics
from .evidence import evaluate_evidence, evidence_metrics

VERSION = 'd3.2.v1'
CALIBRATION_PROTOCOL = 'd32-correctness-v1-proposed'
PINS = ('dataset_manifest_sha256', 'dataset_version', 'preprocess_version',
        'normalizer_version', 'ocr_version', 'schema_version')


def load_gold(root, manifest_path):
    manifest, samples, pins = scalar_ocr.load_gold(root, manifest_path)
    for sample, entry in zip(samples, manifest['samples']):
        for key in ('family_id', 'quality', 'split', 'dev_partition', 'base_id', 'row_count'):
            sample[key] = entry.get(key)
        image = entry['assets'].get('png', {})
        sample['canonical_sha256'] = image.get('sha256')
        if image:
            image_path = asset_path(Path(root), image['path'])
            require(sha(image_path) == image['sha256'], f'hash mismatch: {sample["sample_id"]}/png')
            with image_path.open('rb') as stream:
                header = stream.read(24)
            require(header[:8] == b'\x89PNG\r\n\x1a\n' and header[12:16] == b'IHDR', 'unsupported canonical PNG header')
            sample['canonical_dimensions'] = struct.unpack('>II', header[16:24])
            pins.append(dict(sample_id=sample['sample_id'], asset='png', **image))
        asset = entry['assets'].get('regions.json')
        if asset:
            path = asset_path(Path(root), asset['path'])
            require(sha(path) == asset['sha256'], f'hash mismatch: {sample["sample_id"]}/regions.json')
            sample['regions'] = read_json(path)
            pins.append(dict(sample_id=sample['sample_id'], asset='regions.json', **asset))
    return manifest, samples, pins


def source_hash():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def calibration_label(sample, artifact, entry, outcome):
    reasons = []
    if sample.get('split') != 'dev' or sample.get('dev_partition') != 'dev-calibration':
        reasons.append('not_dev_calibration')
    if artifact.get('calibration_protocol_version') != CALIBRATION_PROTOCOL:
        reasons.append('protocol_not_pinned')
    if any(not isinstance(artifact.get(k), str) or not artifact[k] for k in PINS):
        reasons.append('versions_not_pinned')
    if entry['status'] in ('unlabeled', 'obscured'):
        reasons.append(entry['status'])
    if outcome != 'ok':
        reasons.append('prediction_' + outcome)
    if entry['ambiguous']:
        reasons.append('ambiguous_row_identity')
    if not entry['available'] or entry['prediction'] is None or (isinstance(entry['prediction'], str) and not entry['prediction'].strip()):
        reasons.append('no_candidate')
    return dict(sample_id=sample['sample_id'], field=entry['field'],
                prediction_field=entry.get('prediction_field', entry['field']),
                candidate_version=artifact['model_version'], candidate_value=entry['prediction'],
                gold=entry['gold'], status=entry['status'], correctness=int(entry['correct']) if entry['correct'] is not None else None,
                eligible=not reasons, exclusion_reasons=reasons, outcome=outcome,
                split=sample.get('split'), dev_partition=sample.get('dev_partition'),
                protocol_version=CALIBRATION_PROTOCOL, evaluator_version=VERSION,
                policy_version=POLICY['version'], normalization_policy_version=NORMALIZATION_VERSION,
                versions={k: artifact.get(k) for k in PINS},
                evaluator_source_sha256=source_hash())


def evaluate(samples, artifact):
    report = scalar_ocr.evaluate(samples, artifact)
    report.update(evaluator_version=VERSION, table_evidence_policy=POLICY,
                  calibration_protocol=dict(version=CALIBRATION_PROTOCOL, status='proposed; consumer/Lead confirmation required; no fitting'))
    records = defaultdict(list)
    for r in artifact['predictions']:
        records[r['sample_id']].append(r)
    table_counts, evidence_counts, slices = Counter(), Counter(), defaultdict(list)
    details, labels = [], []
    for sample, outcome in zip(samples, report['samples']):
        sid = sample['sample_id']
        record = records[sid][0] if outcome['outcome'] == 'ok' else {}
        payload = record.get('payload', {})
        table = evaluate_table(sample, payload)
        evidence = evaluate_evidence(sample, record, table)
        table_counts.update(table['counts'])
        evidence_counts.update(evidence['counts'])
        details.append(dict(sample_id=sid, outcome=outcome['outcome'], table=table, evidence=evidence))
        for m in table['matches']:
            if m['ambiguous']:
                report['errors'].append(dict(sample_id=sid, category='ambiguous_row_matching',
                    gold_row=m['gold'], prediction_row=m['prediction'], features=m['features'],
                    gold=sample['gold']['items'][m['gold']], prediction=payload['items'][m['prediction']]))
        for error in table['errors']:
            report['errors'].append(dict(sample_id=sid, document_type=sample['document_type'],
                                         outcome=outcome['outcome'], **error))
        for e in evidence['details']:
            if not e['available'] or not e['text_correct'] or len(e['region_matches']) != len(e['gold']):
                report['errors'].append(dict(sample_id=sid, category='evidence_unavailable_or_mismatch', **e))
        entries = table['cells'] + [cell(sample, '/' + f, f, sample['gold'].get(f), payload.get(f),
                                        outcome['outcome'] == 'ok') for f in FIELDS[sample['document_type']]]
        labels.extend(calibration_label(sample, artifact, e, outcome['outcome']) for e in entries)
        for j in table.get('unmatched_prediction', []):
            for f, value in payload['items'][j].items():
                e = dict(field=f'/items/extra-{j}/{f}', prediction_field=f'/items/{j}/{f}', gold=None,
                         prediction=value, status='unlabeled', correct=None, available=True, ambiguous=True)
                labels.append(calibration_label(sample, artifact, e, outcome['outcome']))
        keys = [('type', sample['document_type']), ('family', sample.get('family_id') or 'unknown'),
                ('quality', sample.get('quality') or 'unknown'),
                ('missing', 'has_absent' if any(v.get('status') == 'absent' for v in sample['labels'].values()) else 'no_absent'),
                ('table', 'unlabeled' if 'items' not in sample['gold'] else str(len(sample['gold']['items'])))]
        for axis, value in keys:
            slices[axis + '/' + value].append(sample)
    report['tables'] = table_metrics(table_counts)
    report['evidence'] = evidence_metrics(evidence_counts)
    report['table_evidence_samples'] = details
    report['correctness_labels'] = labels
    report['calibration_coverage'] = dict(records=len(labels), eligible=sum(e['eligible'] for e in labels),
        exclusions=dict(Counter(r for e in labels for r in e['exclusion_reasons'])))
    report['slices'] = {}
    for key, subset in sorted(slices.items()):
        # D3.1 per-slice metrics reuse the exact scalar/OCR implementation.
        ids = {s['sample_id'] for s in subset}
        scalar = scalar_ocr.evaluate(subset, dict(artifact, predictions=[r for r in artifact['predictions'] if r['sample_id'] in ids]))
        tc, ec = Counter(), Counter()
        for d in details:
            if d['sample_id'] in ids:
                tc.update(d['table']['counts'])
                ec.update(d['evidence']['counts'])
        report['slices'][key] = dict(samples=len(subset), accounting=scalar['accounting'],
            scalar=scalar['scalar']['all'], ocr=scalar['ocr']['all'], tables=table_metrics(tc), evidence=evidence_metrics(ec))
    return report


def compare(artifacts):
    """Missing pins are mismatches, never inferred equality from two nulls."""
    missing = [c for c in ('B0', 'M0', 'M1') if c not in artifacts]
    problems = []
    for pin in PINS:
        values = {name: a.get(pin) for name, a in artifacts.items()}
        if any(not isinstance(v, str) or not v for v in values.values()) or len({v for v in values.values() if isinstance(v, str)}) > 1:
            problems.append(dict(pin=pin, values=values))
    return dict(fair=not missing and not problems, missing_candidates=missing, mismatches=problems,
                evaluator_version=VERSION, policy_version=POLICY['version'],
                note='Same evaluator and policy used for all supplied candidates; no full comparison unless all pins and B0/M0/M1 present.')


def evaluate_files(root, manifest_path, prediction_paths):
    manifest, samples, pins = load_gold(root, manifest_path)
    artifacts, reports = {}, {}
    manifest_hash = sha(manifest_path)
    for name, path in prediction_paths.items():
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]+', name), 'unsafe candidate name')
        artifact = read_json(path)
        json.dumps(artifact, allow_nan=False)
        require(artifact.get('dataset_manifest_sha256') == manifest_hash, 'prediction dataset pin mismatch')
        if artifact.get('dataset_version') is not None:
            require(artifact['dataset_version'] == manifest.get('dataset_version', manifest['version']), 'dataset version mismatch')
        artifacts[name] = artifact
        reports[name] = evaluate(samples, artifact)
        reports[name]['inputs'] = dict(manifest_sha256=manifest_hash, dataset_version=manifest['version'],
            predictions_sha256=sha(path), assets=pins, evaluator_source_sha256=source_hash(),
            manifest_helpers_sha256=sha(Path(__file__).parents[1] / 'data/manifest.py'),
            prediction_metadata={k: v for k, v in artifact.items() if k != 'predictions'})
        for label in reports[name]['correctness_labels']:
            label.update(candidate=name, predictions_sha256=sha(path), manifest_sha256=manifest_hash)
    freeze = dict(status='prepared_not_frozen', decision=None, evaluator_version=VERSION,
                  evaluator_source_sha256=source_hash(), policy=POLICY,
                  normalization_policy=scalar_ocr.POLICY, calibration_protocol=CALIBRATION_PROTOCOL,
                  manifest_sha256=manifest_hash,
                  candidates={k: sha(p) for k, p in prediction_paths.items()},
                  review_required=['AI-1 evidence geometry/association', 'AI-2 matching/normalization/calibration', 'Lead metrics/splits/freeze decision'],
                  changes='Metric definition changes require evaluator/policy version bump and all candidates rescored.')
    return dict(comparison=compare(artifacts), reports=reports, freeze_record=freeze)


def write_bundle(bundle, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    write(output / 'comparison.json', bundle['comparison'])
    write(output / 'freeze-record.json', bundle['freeze_record'])
    for name, report in bundle['reports'].items():
        folder = output / name
        folder.mkdir()
        write(folder / 'report.json', report)
        summary = ['# VietDoc D3.2 table/evidence evaluation', '',
                   'Fixture candidates are test inputs; interpret measured coverage with their declared purpose.', '',
                   '| Table metric | Numerator | Denominator | Value |',
                   '| --- | --- | --- | --- |']
        for key in ('matched_cell_accuracy', 'e2e_cell_accuracy', 'exact_row_accuracy'):
            m = report['tables'][key]
            summary.append(f"| {key} | {m['numerator']} | {m['denominator']} | {m['value']} |")
        summary += ['', 'Counts: ' + json.dumps(report['tables']['counts'], ensure_ascii=False), '',
                    'Evidence: ' + json.dumps(report['evidence'], ensure_ascii=False), '',
                    'Calibration: ' + json.dumps(report['calibration_coverage'], ensure_ascii=False), '',
                    scalar_ocr.markdown(report).replace('# VietDoc D3.1 offline evaluation', '## Scalar/OCR and complete report', 1)]
        (folder / 'report.md').write_text('\n'.join(summary), encoding='utf-8')
        (folder / 'correctness-labels.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False, allow_nan=False)+'\n'
            for e in report['correctness_labels']), encoding='utf-8')
        write(folder / 'errors.json', report['errors'])
