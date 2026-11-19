"""Read AI2's versioned offline OCR companion without inference dependencies."""
from collections import Counter
import json

from vietdoc.data.manifest import read_json, require, sample_id, sha


def load(path, artifact, prediction_hash, gold_ids):
    data = read_json(path)
    json.dumps(data, allow_nan=False)
    require(isinstance(data, dict) and data.get('artifact_version') == 'vietdoc.ocr-diagnostics.v1',
            'unsupported OCR diagnostics format')
    require(set(data) == {'artifact_version', 'predictions_sha256', 'dataset_manifest_sha256',
                          'ocr_inputs_sha256', 'samples'}, 'missing/unknown OCR diagnostics keys')
    require(data['predictions_sha256'] == prediction_hash, 'diagnostics prediction hash mismatch')
    require(data['dataset_manifest_sha256'] == artifact['dataset_manifest_sha256'],
            'diagnostics dataset hash mismatch')
    require(data['ocr_inputs_sha256'] == artifact.get('ocr_inputs_sha256'), 'diagnostics OCR input hash mismatch')
    require(isinstance(data['samples'], list), 'diagnostics samples must be an array')
    predictions = artifact['predictions']
    predicted = {}
    for prediction in predictions:
        predicted.setdefault(prediction['sample_id'], []).append(prediction)
    duplicates = {sid for sid, records in predicted.items() if len(records) > 1}
    seen, statuses, snapshots = set(), Counter(), Counter()
    for entry in data['samples']:
        require(isinstance(entry, dict), 'invalid diagnostics record')
        sid = sample_id(entry.get('sample_id'))
        require(sid not in seen and sid in predicted, f'{sid}: duplicate/unknown diagnostics ID')
        seen.add(sid)
        require(entry.get('status') in ('ok', 'failed'), f'{sid}: invalid diagnostics outcome')
        if sid not in duplicates:
            require(entry['status'] == predicted[sid][0].get('status'), f'{sid}: diagnostics outcome mismatch')
            require(entry.get('error') == predicted[sid][0].get('error'), f'{sid}: diagnostics error mismatch')
        require('ocr' in entry, f'{sid}: missing OCR snapshot')
        page = entry['ocr']
        if page is None:
            require(entry['status'] == 'failed', f'{sid}: successful diagnostics need OCR snapshot')
            if sid in gold_ids:
                snapshots['duplicate' if sid in duplicates else 'unavailable'] += 1
            continue
        require(isinstance(page, dict) and type(page.get('artifact_version')) is int and
                page['artifact_version'] in (1, 2) and type(page.get('page')) is int and page['page'] == 0,
                f'{sid}: invalid OCR snapshot version/page')
        blocks, unreadable = page.get('blocks'), page.get('unreadable_regions')
        require(isinstance(blocks, list) and isinstance(unreadable, list) and
                all(isinstance(r, dict) for r in blocks + unreadable), f'{sid}: invalid OCR snapshot regions')
        expected = ('partial' if blocks else 'unreadable') if unreadable else 'complete'
        require(page.get('recognition_status') == expected, f'{sid}: inconsistent recognition status')
        require(page['artifact_version'] == 2 or not unreadable, f'{sid}: unreadable regions require v2')
        require(page.get('ocr_version') == artifact['ocr_version'] and
                page.get('preprocess_version') == artifact.get('preprocess_version'), f'{sid}: diagnostics version mismatch')
        flags = page.get('review_flags')
        require(isinstance(flags, list) and all(isinstance(f, str) for f in flags), f'{sid}: invalid OCR flags')
        if sid in gold_ids:
            if sid in duplicates:
                snapshots['duplicate'] += 1
            else:
                statuses[expected] += 1
                snapshots[entry['status']] += 1
    require(seen == set(predicted), 'missing diagnostics IDs')
    return dict(companion_sha256=sha(path), predictions_sha256=prediction_hash,
                artifact_version=data['artifact_version'], samples=data['samples'],
                known_id_recognition_status_counts=dict(statuses), known_id_snapshot_outcomes=dict(snapshots),
                unassociated_duplicate_prediction_ids=sorted(duplicates),
                unknown_ids=sorted(seen - gold_ids),
                scope='Producer diagnostics retained, not correctness gold, geometry certification or robustness metric.')
