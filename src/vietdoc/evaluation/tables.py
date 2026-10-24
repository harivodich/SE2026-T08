"""D3.2 table policy v1; no production normalization or inferred labels."""
from collections import Counter
import json
from .matching import match
from .policy import normalize, text
from vietdoc.data.manifest import require

COLUMNS = ('description', 'quantity', 'unit', 'unit_price', 'line_total')
STATUSES = ('present', 'absent', 'obscured', 'unlabeled')
POLICY = {
    'version': 'd32-table-evidence-v1-proposed',
    'status': 'proposed; pending AI-1/AI-2/Lead review; not frozen',
    'matching': 'maximum-weight global one-to-one; dummy unmatched vertices; no index zip',
    'features': 'present gold only: description token-set Jaccard floor(1000*x), weight 4; other exact canonical cells weight 1000 each',
    'edge_gate': 'description similarity >=500 OR >=2 other exact present cells; otherwise no edge',
    'ties': 'Hungarian ascending gold/pred indices, strict improvements; forbid each selected edge and re-solve to detect alternative equal optimum',
    'ambiguity': 'retain deterministic score with flag; exclude ambiguous identity from calibration and evidence',
    'wrap': 'NFC whitespace collapse within description; split physical rows remain separate, no arithmetic or concatenation repair',
    'duplicates': 'normalized full five-cell signatures; count repetitions beyond first, separately gold/pred; excess over gold multiplicity reported',
    'cell_accuracy': 'correct present/absent cells / labeled present+absent cells in matched rows; invalid never matches',
    'e2e_cell_accuracy': 'same numerator / labeled cells in ALL gold rows; missing rows contribute zero',
    'exact_row_accuracy': 'matched rows with all 5 correct / ALL gold rows with all 5 present/absent labels; partial rows excluded',
    'empty': 'zero support => null; empty-table exact success is not added to row metrics',
    'evidence': 'annotated present pointers only; exact canonical image hash/page/dimensions required; polygon IoU >=0.5 one-to-one; no bounding-envelope shortcut',
    'text_association': 'ordered annotation text joined by whitespace versus explicit evidence_text per field; independent from raw_value and OCR score',
}


def canonical(field, value):
    return normalize('total_amount' if field in ('quantity', 'unit_price', 'line_total') else field, value)


def safe(field, value):
    try:
        return canonical(field, value), False
    except ValueError:
        return None, True


def status(sample, path):
    result = sample['labels'].get(path, {}).get('status', 'unlabeled')
    require(result in STATUSES, f'invalid label: {sample["sample_id"]}{path}')
    return result


def cell(sample, path, field, gold, prediction, available=True, ambiguous=False):
    label = status(sample, path)
    g = canonical(field, gold) if label in ('present', 'absent') else None
    if label in ('present', 'absent'):
        require((label == 'present') == (g is not None), f'inconsistent gold label: {path}')
    p, invalid = safe(field, prediction)
    correct = (available and not invalid and g == p) if label in ('present', 'absent') else None
    return dict(field=path, status=label, gold=gold, prediction=prediction,
                correct=correct, invalid=invalid, available=available, ambiguous=ambiguous)


def signature(row):
    result = []
    for field in COLUMNS:
        value, invalid = safe(field, row.get(field))
        result.append(('invalid', json.dumps(row.get(field), sort_keys=True, ensure_ascii=False))
                      if invalid else ('canonical', value))
    return tuple(result)


def evaluate_table(sample, payload):
    gold = sample['gold'].get('items')
    if gold is None:
        return dict(counts={'unlabeled_tables': 1}, matches=[], cells=[], errors=[])
    require(isinstance(gold, list) and len(gold) <= 30 and all(isinstance(r, dict) for r in gold), 'invalid gold items')
    raw = payload.get('items')
    invalid = raw is not None and (not isinstance(raw, list) or len(raw) > 30 or
                                  any(not isinstance(r, dict) or set(r) - set(COLUMNS) for r in raw))
    pred = [] if invalid or raw is None else raw
    cells_by_row = [[cell(sample, f'/items/{i}/{f}', f, row.get(f), None, False)
                     for f in COLUMNS] for i, row in enumerate(gold)]
    features, weights = [], []
    for i, row in enumerate(gold):
        feature_row, weight_row = [], []
        for candidate in pred:
            equal, similarity = [], 0
            for c, f in zip(cells_by_row[i], COLUMNS):
                value, bad = safe(f, candidate.get(f))
                if c['status'] != 'present' or value is None or bad:
                    continue
                g = canonical(f, row.get(f))
                if f == 'description':
                    a, b = set(text(g).split()), set(text(value).split())
                    similarity = 1000 * len(a & b) // len(a | b) if a | b else 0
                elif value == g:
                    equal.append(f)
            score = 4 * similarity + 1000 * len(equal) if similarity >= 500 or len(equal) >= 2 else 0
            feature_row.append(dict(description_jaccard_milli=similarity, exact_other_cells=equal, score=score))
            weight_row.append(score)
        features.append(feature_row)
        weights.append(weight_row)
    matches = match(weights)
    by_gold = {m['gold']: m for m in matches}
    used = {m['prediction'] for m in matches}
    c = Counter(gold_rows=len(gold), predicted_rows=len(pred), matched_rows=len(matches),
                missing_gold_rows=len(gold) - len(matches), extra_predicted_rows=len(pred) - len(matches),
                invalid_tables=int(invalid), missing_tables=int(raw is None), empty_gold_tables=int(not gold))
    gs, ps = Counter(map(signature, gold)), Counter(map(signature, pred))
    c.update(gold_duplicates=sum(n-1 for n in gs.values()), predicted_duplicates=sum(n-1 for n in ps.values()),
             excess_duplicates=sum(max(0, n-max(1, gs[s])) for s, n in ps.items()))
    cells, errors = [], []
    if invalid:
        errors.append(dict(category='invalid_table', gold=gold, prediction=raw))
    for i, row in enumerate(gold):
        m = by_gold.get(i)
        if m:
            m['features'] = features[i][m['prediction']]
            c['ambiguous_matches'] += m['ambiguous']
        row_cells = []
        for f in COLUMNS:
            path = f'/items/{i}/{f}'
            entry = cell(sample, path, f, row.get(f), pred[m['prediction']].get(f) if m else None,
                         bool(m), bool(m and m['ambiguous']))
            entry['prediction_field'] = f'/items/{m["prediction"]}/{f}' if m else None
            row_cells.append(entry)
            c[entry['status'] + '_cells'] += 1
            if entry['correct'] is not None:
                c['e2e_cells'] += 1
                c['matched_cells'] += bool(m)
                c['correct_cells'] += bool(entry['correct'])
                c[f + '_cells'] += bool(m)
                c[f + '_correct'] += bool(entry['correct'])
                if not entry['correct']:
                    errors.append(dict(entry, category='unmatched_gold_row' if not m else
                                       'invalid_cell' if entry['invalid'] else
                                       'false_fill' if entry['status'] == 'absent' else 'wrong_or_missing_cell',
                                       gold_row=i, prediction_row=m['prediction'] if m else None))
        if all(e['correct'] is not None for e in row_cells):
            c['fully_labeled_rows'] += 1
            c['exact_rows'] += all(e['correct'] for e in row_cells)
        else:
            c['partial_rows'] += 1
        cells.extend(row_cells)
    for j, row in enumerate(pred):
        if j not in used:
            duplicates = [k for k in range(j) if signature(pred[k]) == signature(row)]
            errors.append(dict(category='duplicate_predicted_row' if duplicates else 'extra_predicted_row',
                               duplicate_of=duplicates, prediction_row=j, gold=None, prediction=row))
    return dict(counts=dict(c), matches=matches, features=features, cells=cells, errors=errors,
                unmatched_gold=[i for i in range(len(gold)) if i not in by_gold],
                unmatched_prediction=[j for j in range(len(pred)) if j not in used])


def table_metrics(counts):
    c = Counter(counts)
    def rate(n, d):
        return dict(numerator=c[n], denominator=c[d], value=c[n]/c[d] if c[d] else None)
    return dict(counts=dict(c), matched_cell_accuracy=rate('correct_cells', 'matched_cells'),
                e2e_cell_accuracy=rate('correct_cells', 'e2e_cells'),
                exact_row_accuracy=rate('exact_rows', 'fully_labeled_rows'),
                columns={f: rate(f + '_correct', f + '_cells') for f in COLUMNS})
