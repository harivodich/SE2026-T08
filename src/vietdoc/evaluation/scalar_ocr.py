"""D3.1 frozen-artifact evaluator. Stdlib only, no API/inference dependencies."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from vietdoc.data.manifest import asset_path, read_json, require, sample_id, sha
from .policy import FIELDS, POLICY, normalize, text

VERSION = 'd3.1.v1'
ARTIFACT_VERSION = 'vietdoc.predictions.v1'


def load_gold(root, manifest_path):
    manifest = read_json(manifest_path)
    require(isinstance(manifest.get('version'), str) and manifest['version'], 'manifest version required')
    samples, pins, ids = [], [], set()
    for entry in manifest['samples']:
        sid = sample_id(entry['sample_id'])
        require(sid not in ids, f'duplicate gold ID: {sid}')
        ids.add(sid)
        kind = entry['document_type']
        require(kind in FIELDS, f'unsupported type: {kind}')
        require(entry.get('schema_id') == 'urn:vietdoc:business:v1', 'unsupported business schema')
        loaded = {}
        for key in ('gold.json', 'labels.json', 'txt'):
            if key == 'txt' and key not in entry['assets']:
                continue
            asset = entry['assets'][key]
            path = asset_path(Path(root), asset['path'])
            require(sha(path) == asset['sha256'], f'hash mismatch: {sid}/{key}')
            pins.append(dict(sample_id=sid, asset=key, **asset))
            loaded[key] = path.read_text(encoding='utf-8') if key == 'txt' else read_json(path)
        scope = entry.get('transcript_scope', manifest.get('transcript_scope'))
        if scope is None and manifest['version'] == 'd1.2.v1':
            scope = 'full_page'
        samples.append(dict(sample_id=sid, document_type=kind, gold=loaded['gold.json'],
                            labels=loaded['labels.json'], transcript=loaded.get('txt'),
                            transcript_scope=scope))
    return manifest, samples, pins


def metric(numerator, denominator, support, exclusions):
    return dict(value=numerator / denominator if denominator else None,
                numerator=numerator, denominator=denominator, support=support,
                exclusions=dict(exclusions), zero_denominator='null')


def scalar_metrics(c):
    for key in ('present', 'absent', 'unlabeled', 'obscured', 'tp', 'fp', 'fn',
                'false_fill', 'present_missing', 'present_null', 'present_empty',
                'wrong_value', 'invalid_value'):
        c.setdefault(key, 0)
    exclusions = {k: c[k] for k in ('unlabeled', 'obscured')}
    support = c['present']
    return dict(counts=dict(c),
                normalized_exact_match=metric(c['tp'], support, support, exclusions),
                precision=metric(c['tp'], c['tp'] + c['fp'], support, exclusions),
                recall=metric(c['tp'], c['tp'] + c['fn'], support, exclusions),
                f1=metric(2 * c['tp'], 2 * c['tp'] + c['fp'] + c['fn'], support, exclusions))


def edits(reference, prediction):
    """Levenshtein distance with O(len(prediction)) memory, no external tokenizer."""
    if reference == prediction:
        return 0
    previous = list(range(len(prediction) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(prediction, 1):
            current.append(min(previous[j] + 1, current[j-1] + 1,
                               previous[j-1] + (a != b)))
        previous = current
    return previous[-1]


def evaluate(samples, artifact):
    require(artifact.get('artifact_version') == ARTIFACT_VERSION, 'unsupported prediction artifact version')
    for key in ('model_version', 'normalizer_version', 'ocr_version'):
        require(isinstance(artifact.get(key), str) and artifact[key], f'{key} required (use not-applicable if needed)')
    require(isinstance(artifact.get('predictions'), list), 'predictions must be a list')
    ids = [sample_id(s['sample_id']) for s in samples]
    require(len(ids) == len(set(ids)), 'duplicate gold ID')
    ids = set(ids)
    records = defaultdict(list)
    issues, errors, outcomes = [], [], []
    for index, record in enumerate(artifact['predictions']):
        require(isinstance(record, dict), f'invalid record at {index}')
        sid = sample_id(record.get('sample_id'))
        records[sid].append(record)
    for sid, entries in sorted(records.items()):
        if sid not in ids:
            issues.append(dict(sample_id=sid, category='unknown_prediction_id', records=len(entries)))
        if len(entries) > 1:
            issues.append(dict(sample_id=sid, category='duplicate_prediction_id', records=len(entries)))
    scalar = defaultdict(Counter)
    ocr = defaultdict(Counter)
    for group in ('all', 'receipt', 'invoice', 'critical/date', 'critical/total'):
        scalar[group] = Counter()
    for group in ('all', 'receipt', 'invoice'):
        ocr[group] = Counter()
    for sample in samples:
        sid, kind = sample['sample_id'], sample['document_type']
        require(kind in FIELDS, f'unsupported type: {kind}')
        candidates = records.get(sid, [])
        pred = candidates[0] if len(candidates) == 1 else {}
        if not candidates:
            outcome = 'missing'
        elif len(candidates) > 1:
            outcome = 'duplicate'
        elif pred.get('status') == 'failed':
            outcome = 'failed'
        elif (pred.get('status') != 'ok' or not isinstance(pred.get('payload', {}), dict)
              or any(k not in (*FIELDS[kind], 'items') for k in pred.get('payload', {}))
              or ('ocr_text' in pred and not isinstance(pred['ocr_text'], (str, type(None))))):
            outcome = 'invalid'
        else:
            outcome = 'ok'
        payload = pred.get('payload', {}) if outcome == 'ok' else {}
        outcomes.append(dict(sample_id=sid, document_type=kind, outcome=outcome,
                             reason=pred.get('error'), records=len(candidates)))
        if outcome != 'ok':
            issues.append(dict(sample_id=sid, category=outcome + '_prediction', records=len(candidates)))
        for field in FIELDS[kind]:
            raw_gold = sample['gold'].get(field)
            status = sample['labels'].get('/' + field, {}).get('status', 'unlabeled')
            require(status in ('present', 'absent', 'unlabeled', 'obscured'), f'invalid label: {sid}/{field}')
            raw_pred = payload.get(field)
            groups = ['all', kind, kind + '/' + field]
            if field == 'total_amount' or field.endswith('date'):
                groups.append('critical/' + ('date' if field.endswith('date') else 'total'))
            counters = [scalar[g] for g in groups]
            for c in counters:
                c[status] += 1
            if status in ('unlabeled', 'obscured'):
                continue
            gold = normalize(field, raw_gold)
            require((status == 'present' and gold is not None) or
                    (status == 'absent' and gold is None), f'inconsistent gold label: {sid}/{field}')
            invalid = False
            try:
                value = normalize(field, raw_pred)
            except ValueError:
                value, invalid = None, True
            category = None
            if status == 'absent':
                if value is not None or invalid:
                    category = 'false_fill'
                    for c in counters:
                        c['fp'] += 1
                        c['false_fill'] += 1
            elif not invalid and value == gold:
                for c in counters:
                    c['tp'] += 1
            else:
                category = ('invalid_value' if invalid else 'wrong_value' if value is not None
                            else 'present_missing' if field not in payload else 'present_null'
                            if raw_pred is None else 'present_empty')
                for c in counters:
                    c['fn'] += 1
                    c[category] += 1
                    if invalid or value is not None:
                        c['fp'] += 1
            if category:
                errors.append(dict(sample_id=sid, document_type=kind, field=field, gold=raw_gold,
                                   prediction=raw_pred, category=category, outcome=outcome))
        transcript = sample.get('transcript')
        c = Counter(samples=1)
        if transcript is None or sample.get('transcript_scope') != 'full_page':
            c['excluded_no_full_page_gold'] = 1
        else:
            require(isinstance(transcript, str), f'invalid transcript: {sid}')
            predicted_text = pred.get('ocr_text') if outcome == 'ok' else None
            c['eligible_samples'] += 1
            if predicted_text is None:
                c['missing_or_failed_ocr'] += 1
            reference, hypothesis = text(transcript), text(predicted_text or '')
            ce, we = edits(reference, hypothesis), edits(reference.split(), hypothesis.split())
            c['character_edits'] += ce
            c['word_edits'] += we
            c['reference_characters'] += len(reference)
            c['reference_words'] += len(reference.split())
            c['empty_reference_samples'] += not reference
            if ce or we or predicted_text is None:
                errors.append(dict(sample_id=sid, document_type=kind, field='ocr_text',
                                   gold=transcript, prediction=predicted_text, category='ocr_error',
                                   character_edits=ce, word_edits=we, outcome=outcome))
        for group in ('all', kind):
            ocr[group].update(c)
    ocr_report = {}
    for group, c in sorted(ocr.items()):
        excluded = {'no_full_page_gold': c['excluded_no_full_page_gold']}
        ocr_report[group] = dict(counts=dict(c),
            cer=metric(c['character_edits'], c['reference_characters'], c['eligible_samples'], excluded),
            wer=metric(c['word_edits'], c['reference_words'], c['eligible_samples'], excluded))
    return dict(evaluator_version=VERSION, policy=POLICY,
                accounting=dict(gold_samples=len(samples), prediction_records=len(artifact['predictions']),
                                outcomes=dict(Counter(s['outcome'] for s in outcomes)),
                                unknown_ids=sorted(set(records) - set(ids))),
                scalar={g: scalar_metrics(c) for g, c in sorted(scalar.items())},
                ocr=ocr_report, issues=issues, samples=outcomes, errors=errors)


def evaluate_files(root, manifest_path, predictions_path):
    manifest, samples, pins = load_gold(root, manifest_path)
    artifact = read_json(predictions_path)
    # Reject non-JSON constants even though Python's decoder accepts NaN/Infinity.
    json.dumps(artifact, allow_nan=False)
    manifest_hash = sha(manifest_path)
    require(artifact.get('dataset_manifest_sha256') == manifest_hash, 'prediction dataset pin mismatch')
    report = evaluate(samples, artifact)
    source_hash = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        source_hash.update(path.name.encode())
        source_hash.update(path.read_bytes())
    report['inputs'] = dict(dataset_version=manifest['version'], manifest_sha256=manifest_hash,
                           predictions_sha256=sha(predictions_path), assets=pins,
                           evaluator_source_sha256=source_hash.hexdigest(),
                           manifest_helpers_sha256=sha(Path(__file__).parents[1] / 'data/manifest.py'),
                           prediction_metadata={k: v for k, v in artifact.items() if k != 'predictions'})
    return report


def markdown(report):
    """Include complete machine data as fenced JSON so no failure/support is hidden."""
    lines = ['# VietDoc D3.1 offline evaluation', '',
             f"Evaluator: {report['evaluator_version']}; policy: {POLICY['version']} (proposed).", '',
             '| Group | EM | Precision | Recall | F1 |',
             '| --- | --- | --- | --- | --- |']
    for group, result in report['scalar'].items():
        cells = []
        for name in ('normalized_exact_match', 'precision', 'recall', 'f1'):
            m = result[name]
            cells.append(f"{m['value']} ({m['numerator']}/{m['denominator']})")
        lines.append('| ' + group + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', 'CER/WER are corpus micro rates; see counts, support, exclusions and errors below.',
              'Zero denominator = null. Absent adds no true positives. Missing/failed inputs remain in E2E.', '',
              'E2E outcomes: ' + json.dumps(report['accounting'], ensure_ascii=False), '',
              '| OCR group | CER (edits/reference chars) | WER (edits/reference words) | Eligible samples | Excluded |',
              '| --- | --- | --- | --- | --- |']
    for group, result in report['ocr'].items():
        cer, wer = result['cer'], result['wer']
        lines.append(f"| {group} | {cer['value']} ({cer['numerator']}/{cer['denominator']}) | "
                     f"{wer['value']} ({wer['numerator']}/{wer['denominator']}) | "
                     f"{cer['support']} | {cer['exclusions']} |")
    lines += ['',
              '## Full accounting, OCR, provenance and sample errors', '', '```json',
              json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), '```', '']
    return '\n'.join(lines)
