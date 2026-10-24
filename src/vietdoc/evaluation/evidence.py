"""Explicit renderer-to-canonical adapter and convex polygon evidence scoring."""
from collections import Counter, defaultdict
import math
from .matching import match
from .policy import text
from .tables import status

CONVENTION = 'canonical-normalized-quad-v1'


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def area(poly):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(poly, poly[1:]+poly[:1]))) / 2


def polygon(quad):
    if (not isinstance(quad, list) or len(quad) != 4 or
        any(not isinstance(p, list) or len(p) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in p) for p in quad)):
        return None
    # TL,TR,BR,BL winding in top-left image coordinates, strict convexity.
    if any(cross(quad[i], quad[(i+1) % 4], quad[(i+2) % 4]) <= 0 for i in range(4)):
        return None
    return quad


def iou(a, b):
    output = a[:]
    for start, end in zip(b, b[1:]+b[:1]):
        points, output = output, []
        if not points:
            break
        prev = points[-1]
        for current in points:
            cp, cc = cross(start, end, prev), cross(start, end, current)
            if (cp >= 0) != (cc >= 0):
                t = cp / (cp-cc)
                output.append([prev[k]+t*(current[k]-prev[k]) for k in (0, 1)])
            if cc >= 0:
                output.append(current)
            prev = current
    intersection = area(output) if output else 0
    return intersection / (area(a)+area(b)-intersection)


def adapt_gold(sample):
    raw = sample.get('regions')
    if not raw:
        return None, 'no_gold_regions'
    transform = raw.get('transform')
    affine = (isinstance(transform, dict) and all(isinstance(transform.get(k), list) and len(transform[k]) == 6 and
              all(type(v) in (int, float) and math.isfinite(v) for v in transform[k])
              for k in ('source_to_canonical', 'canonical_to_source')))
    if (raw.get('convention') != 'renderer-local-v1; not approved shared geometry' or
        raw.get('origin') != 'top-left' or raw.get('units') != 'pixels' or
        (transform != 'identity; PNG is the rendered page' and not affine) or raw.get('page') != 0 or
        any(type(raw.get(k)) is not int or raw[k] <= 0 for k in ('width', 'height')) or
        not sample.get('canonical_sha256') or
        sample.get('canonical_dimensions', (raw.get('width'), raw.get('height'))) != (raw.get('width'), raw.get('height'))):
        return None, 'unsupported_gold_geometry'
    converted = defaultdict(list)
    for r in raw.get('regions', []):
        path = r.get('pointer')
        if not path or status(sample, path) != 'present':
            continue
        box = r.get('bbox_px')
        if not isinstance(box, list) or len(box) != 4 or any(type(x) not in (int, float) for x in box):
            return None, 'invalid_gold_geometry'
        x1, y1, x2, y2 = box
        quad = [[x1/raw['width'], y1/raw['height']], [x2/raw['width'], y1/raw['height']],
                [x2/raw['width'], y2/raw['height']], [x1/raw['width'], y2/raw['height']]]
        if affine:
            raw_quad = r.get('quad_px')
            if not isinstance(raw_quad, list) or len(raw_quad) != 4 or any(not isinstance(p, list) or len(p) != 2 or any(type(v) not in (int, float) for v in p) for p in raw_quad):
                return None, 'invalid_gold_geometry'
            quad = [[x/raw['width'], y/raw['height']] for x, y in raw_quad]
        if r.get('page') != 0 or not polygon(quad) or not isinstance(r.get('text'), str):
            return None, 'invalid_gold_geometry'
        converted[path].append(dict(quad=quad, text=r['text']))
    return dict(page=0, width=raw['width'], height=raw['height'],
                sha256=sample['canonical_sha256'], regions=dict(converted)), None


def evaluate_evidence(sample, prediction, table):
    gold, reason = adapt_gold(sample)
    c, details = Counter(), []
    if gold is None:
        return dict(counts={reason: 1}, details=[])
    row_map = {m['gold']: m for m in table['matches']}
    metadata = defaultdict(list)
    raw_metadata = prediction.get('field_metadata', [])
    if not isinstance(raw_metadata, list):
        raw_metadata = []
        c['invalid_metadata'] += 1
    for m in raw_metadata:
        if isinstance(m, dict) and isinstance(m.get('path'), str):
            metadata[m['path']].append(m)
        else:
            c['invalid_metadata'] += 1
    page = prediction.get('canonical_page') or {}
    if not isinstance(page, dict):
        page = {}
    compatible = (prediction.get('geometry_convention') == CONVENTION and
                  all(page.get(k) == gold[k] for k in ('page', 'width', 'height', 'sha256')))
    c['gold_annotated_fields'] = len(gold['regions'])
    c['gold_annotated_regions'] = sum(map(len, gold['regions'].values()))
    c['present_fields_without_regions'] = sum(v.get('status') == 'present' and k not in gold['regions']
                                               for k, v in sample['labels'].items())
    for path, regions in gold['regions'].items():
        pred_path, ambiguous = path, False
        if path.startswith('/items/'):
            parts = path.split('/')
            m = row_map.get(int(parts[2]))
            pred_path = f'/items/{m["prediction"]}/{parts[3]}' if m else None
            ambiguous = bool(m and m['ambiguous'])
        entries = metadata.get(pred_path, [])
        entry = entries[0] if len(entries) == 1 else {}
        flags = entry.get('review_flags', [])
        if flags is None:
            flags = ['ambiguous_invalid_flags']
        invalid_flags = not isinstance(flags, list) or any(not isinstance(f, str) for f in flags)
        ambiguous = ambiguous or len(entries) > 1 or invalid_flags or any('ambig' in f.lower() for f in flags if isinstance(f, str))
        source = entry.get('source_regions', [])
        valid = (isinstance(source, list) and all(isinstance(r, dict) and r.get('page') == 0 and
                                                  polygon(r.get('quad')) for r in source))
        available = compatible and valid and bool(source) and not ambiguous
        c['ambiguous_fields'] += ambiguous
        c['covered_fields'] += available
        c['incompatible_fields'] += not compatible
        c['invalid_region_fields'] += not valid
        c['missing_evidence_fields'] += not bool(source)
        matches = []
        if available:
            c['comparable_gold_regions'] += len(regions)
            c['comparable_predicted_regions'] += len(source)
            overlaps = [[iou(g['quad'], p['quad']) for p in source] for g in regions]
            matches = match([[round(v * 1000000) if v >= .5 else 0 for v in row] for row in overlaps])
            c['geometry_matched_regions'] += len(matches)
            c['extra_regions'] += len(source)-len(matches)
            c['ambiguous_region_matches'] += sum(m['ambiguous'] for m in matches)
        explicit_text = entry.get('evidence_text')
        has_text = compatible and isinstance(explicit_text, str) and not ambiguous
        correct_text = has_text and text(explicit_text) == text(' '.join(g['text'] for g in regions))
        c['text_covered_fields'] += has_text
        c['text_correct_fields'] += correct_text
        details.append(dict(field=path, prediction_field=pred_path, compatible=compatible,
                            available=available, ambiguous=ambiguous, region_matches=matches,
                            gold=regions, prediction=source, text_correct=correct_text if has_text else None,
                            gold_text=' '.join(g['text'] for g in regions), prediction_text=explicit_text))
    return dict(counts=dict(c), details=details)


def evidence_metrics(counts):
    c = Counter(counts)
    def rate(n, d):
        return dict(numerator=c[n], denominator=c[d], value=c[n]/c[d] if c[d] else None)
    return dict(counts=dict(c), coverage=rate('covered_fields', 'gold_annotated_fields'),
                geometry_recall=rate('geometry_matched_regions', 'gold_annotated_regions'),
                geometry_accuracy_on_available=rate('geometry_matched_regions', 'comparable_gold_regions'),
                geometry_precision_on_available=rate('geometry_matched_regions', 'comparable_predicted_regions'),
                text_coverage=rate('text_covered_fields', 'gold_annotated_fields'),
                text_accuracy_on_available=rate('text_correct_fields', 'text_covered_fields'),
                text_e2e_accuracy=rate('text_correct_fields', 'gold_annotated_fields'))
