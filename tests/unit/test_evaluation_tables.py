"""Independent hand-counted D3.2 oracles; fixture inputs are NOT model output."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from vietdoc.evaluation import extended
from vietdoc.evaluation.evidence import CONVENTION, evaluate_evidence, iou, polygon
from vietdoc.evaluation.matching import assignment, match
from vietdoc.evaluation.tables import COLUMNS, evaluate_table, table_metrics
from test_evaluation import artifact, prediction, sample

ROOT = Path(__file__).resolve().parents[2]


def row(description='Trà sen', quantity='2', unit='hộp', unit_price='10', line_total='20'):
    return dict(zip(COLUMNS, (description, quantity, unit, unit_price, line_total)))


def table_sample(rows):
    s = sample()
    s.update(split='dev', dev_partition='dev-calibration', family_id='fictional', quality='clean')
    s['gold']['items'] = deepcopy(rows)
    for i, r in enumerate(rows):
        for f, v in r.items():
            s['labels'][f'/items/{i}/{f}'] = {'status': 'present' if v is not None else 'absent'}
    return s


def geometry_sample():
    s = table_sample([])
    s['canonical_sha256'] = 'a'*64
    s['regions'] = dict(convention='renderer-local-v1; not approved shared geometry', page=0,
        width=100, height=100, origin='top-left', units='pixels', transform='identity; PNG is the rendered page',
        regions=[dict(pointer='/merchant_name', text='Cửa Hàng', page=0, bbox_px=[0, 0, 50, 50])])
    p = prediction(s)
    p.update(geometry_convention=CONVENTION, canonical_page=dict(page=0, width=100, height=100, sha256='a'*64),
        field_metadata=[dict(path='/merchant_name', evidence_text='Cửa Hàng', review_flags=[],
                            source_regions=[dict(page=0, quad=[[0, 0], [.5, 0], [.5, .5], [0, .5]])])])
    return s, p


class TableEvaluationTest(unittest.TestCase):
    def test_reorder_wrap_decimal(self):
        a, b = row(), row('Vải', '1', 'm', '30', '30')
        s = table_sample([a, b])
        p = [b, dict(a, description=' Trà\n sen ', quantity='2.00')]
        t = evaluate_table(s, {'items': p})
        self.assertEqual([(m['gold'], m['prediction']) for m in t['matches']], [(0, 1), (1, 0)])
        m = table_metrics(t['counts'])
        self.assertEqual(m['matched_cell_accuracy'], dict(numerator=10, denominator=10, value=1))
        self.assertEqual(m['exact_row_accuracy']['value'], 1)

    def test_duplicate_signatures_use_decimal_equality_and_typed_null(self):
        s = table_sample([row()])
        t = evaluate_table(s, {'items': [row(), row(quantity='2.00', unit_price='10.0')]})
        self.assertEqual(t['counts']['predicted_duplicates'], 1)
        t = evaluate_table(table_sample([]), {'items': [row(description=None), row(description='None')]})
        self.assertEqual(t['counts']['predicted_duplicates'], 0)

    def test_wrong_cell(self):
        t = evaluate_table(table_sample([row()]), {'items': [row(quantity='3')]})
        m = table_metrics(t['counts'])
        self.assertEqual(m['matched_cell_accuracy']['value'], 4/5)
        self.assertEqual(m['exact_row_accuracy']['value'], 0)
        self.assertEqual(m['columns']['quantity']['value'], 0)
        self.assertEqual(t['errors'][0]['gold'], '2')
        self.assertEqual(t['errors'][0]['prediction'], '3')

    def test_dropped_extra_duplicate_and_empty(self):
        a, b, extra = row(), row('Vải', '1', 'm', '30', '30'), row('Khác', '9', 'kg', '7', '63')
        t = evaluate_table(table_sample([a, b]), {'items': [a, a, extra]})
        c, m = t['counts'], table_metrics(t['counts'])
        self.assertEqual((c['missing_gold_rows'], c['extra_predicted_rows'], c['predicted_duplicates'], c['excess_duplicates']), (1, 2, 1, 1))
        self.assertEqual(m['matched_cell_accuracy']['value'], 1)
        self.assertEqual(m['e2e_cell_accuracy']['value'], .5)
        self.assertEqual(m['exact_row_accuracy']['value'], .5)
        for gold, pred, missing, extras in (([], [], 0, 0), ([], [a], 0, 1), ([a], [], 1, 0)):
            with self.subTest(gold=gold):
                t = evaluate_table(table_sample(gold), {'items': pred})
                self.assertEqual(t['counts']['missing_gold_rows'], missing)
                self.assertEqual(t['counts']['extra_predicted_rows'], extras)
                self.assertIsNone(table_metrics(t['counts'])['matched_cell_accuracy']['value'])

    def test_identical_rows_and_global_ambiguity(self):
        s = table_sample([row(), row()])
        t = evaluate_table(s, {'items': [row(), row()]})
        self.assertEqual(t['counts']['gold_duplicates'], 1)
        self.assertEqual(t['counts']['excess_duplicates'], 0)
        self.assertEqual(t['counts']['ambiguous_matches'], 2)
        self.assertEqual(table_metrics(t['counts'])['exact_row_accuracy']['value'], 1)
        self.assertEqual(t, evaluate_table(s, {'items': [row(), row()]}))
        # Global ambiguity even though each row's best edge differs: sums 6=6.
        self.assertTrue(all(m['ambiguous'] for m in match([[4, 3], [3, 2]])))

    def test_assignment_global_beats_greedy_and_brute_oracle(self):
        self.assertEqual(assignment([[9, 8], [8, 0]])[1], 16)
        # Exhaustive independent 2x2 oracle with explicit unmatched choices.
        for flat in itertools.product((0, 1, 2), repeat=4):
            w = [list(flat[:2]), list(flat[2:])]
            expected = max(0, *flat, w[0][0]+w[1][1], w[0][1]+w[1][0])
            self.assertEqual(assignment(w)[1], expected)

    def test_partial_labels_absent_and_invalid(self):
        s = table_sample([row(unit=None)])
        s['labels']['/items/0/quantity']['status'] = 'obscured'
        del s['labels']['/items/0/unit_price']
        t = evaluate_table(s, {'items': [row(unit='bịa', quantity='999', unit_price='invalid')]})
        m = table_metrics(t['counts'])
        # description + line_total correct; absent unit falsely filled; 2/3.
        self.assertEqual(m['matched_cell_accuracy']['value'], 2/3)
        self.assertIsNone(m['exact_row_accuracy']['value'])
        self.assertEqual(t['counts']['obscured_cells'], 1)
        self.assertEqual(t['counts']['unlabeled_cells'], 1)
        self.assertEqual(t['errors'][0]['category'], 'false_fill')
        s = table_sample([row()])
        t = evaluate_table(s, {'items': [row(quantity=2.0)]})
        self.assertEqual(t['errors'][0]['category'], 'invalid_cell')
        s['labels']['/items/0/quantity']['status'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'inconsistent gold'):
            evaluate_table(s, {})

    def test_split_wrap_rows_are_not_silently_merged(self):
        s = table_sample([row('Trà sen hư cấu')])
        t = evaluate_table(s, {'items': [row('Trà sen'), row('hư cấu', None, None, None, None)]})
        self.assertEqual(t['counts']['extra_predicted_rows'], 1)
        self.assertEqual(table_metrics(t['counts'])['matched_cell_accuracy']['value'], 4/5)

    def test_failed_missing_duplicate_invalid(self):
        s = table_sample([row()])
        for records, outcome in (([], 'missing'), ([prediction(s, status='failed')], 'failed'),
                                  ([prediction(s), prediction(s)], 'duplicate'), ([prediction(s, payload=[])], 'invalid')):
            r = extended.evaluate([s], artifact(*records))
            self.assertEqual(r['accounting']['outcomes'], {outcome: 1})
            self.assertEqual(r['tables']['exact_row_accuracy']['value'], 0)
            self.assertEqual(r['tables']['counts']['missing_gold_rows'], 1)
            self.assertEqual(r['calibration_coverage']['eligible'], 0)
        for invalid in ('bad', [None], [dict(row(), unknown='x')], [row()]*31):
            t = evaluate_table(s, {'items': invalid})
            self.assertEqual(t['counts']['invalid_tables'], 1)


class EvidenceEvaluationTest(unittest.TestCase):
    def test_exact_shifted_and_no_overlap(self):
        s, p = geometry_sample()
        for quad, expected in (([[0, 0], [.5, 0], [.5, .5], [0, .5]], 1),
                               ([[.1, 0], [.6, 0], [.6, .5], [.1, .5]], 1),
                               ([[.5, .5], [1, .5], [1, 1], [.5, 1]], 0)):
            p['field_metadata'][0]['source_regions'][0]['quad'] = quad
            r = extended.evaluate([s], artifact(p))['evidence']
            self.assertEqual(r['geometry_recall']['value'], expected)
            self.assertEqual(r['coverage']['value'], 1)
        # Direct independent IoU: overlap .4*.5=.2, union .25+.25-.2=.3 => 2/3.
        self.assertAlmostEqual(iou([[0, 0], [.5, 0], [.5, .5], [0, .5]],
                                   [[.1, 0], [.6, 0], [.6, .5], [.1, .5]]), 2/3)

    def test_polygon_not_bounding_box(self):
        diamond = [[.5, 0], [1, .5], [.5, 1], [0, .5]]
        self.assertIsNotNone(polygon(diamond))
        self.assertEqual(iou(diamond, [[0, 0], [1, 0], [1, 1], [0, 1]]), .5)
        self.assertIsNone(polygon(list(reversed(diamond))))

    def test_incompatible_unavailable_ambiguous_and_wrong_text(self):
        for change in ('page', 'width', 'sha256', 'convention', 'unavailable', 'ambiguous', 'bad_quad', 'region_page'):
            s, p = geometry_sample()
            if change in ('page', 'width', 'sha256'):
                p['canonical_page'][change] = 'wrong'
            elif change == 'convention':
                p['geometry_convention'] = 'processed'
            elif change == 'unavailable':
                p['field_metadata'] = []
            elif change == 'ambiguous':
                p['field_metadata'][0]['review_flags'] = ['ambiguous']
            elif change == 'region_page':
                p['field_metadata'][0]['source_regions'][0]['page'] = 1
            else:
                p['field_metadata'][0]['source_regions'][0]['quad'][0][0] = float('nan')
            r = extended.evaluate([s], artifact(p))['evidence']
            self.assertEqual(r['coverage']['value'], 0, change)
            self.assertEqual(r['geometry_recall']['value'], 0, change)
        s, p = geometry_sample()
        p['field_metadata'][0]['evidence_text'] = 'sai'
        r = extended.evaluate([s], artifact(p))['evidence']
        self.assertEqual(r['text_accuracy_on_available']['value'], 0)
        del s['regions']
        r = extended.evaluate([s], artifact(p))['evidence']
        self.assertIsNone(r['geometry_recall']['value'])
        self.assertEqual(r['counts']['no_gold_regions'], 1)

    def test_affine_renderer_adapter_and_dimension_mismatch(self):
        s, p = geometry_sample()
        s['regions']['transform'] = dict(source_to_canonical=[1, 0, 0, 0, 1, 0],
                                         canonical_to_source=[1, 0, 0, 0, 1, 0])
        s['regions']['regions'][0]['quad_px'] = [[0, 0], [50, 0], [50, 50], [0, 50]]
        r = extended.evaluate([s], artifact(p))
        self.assertEqual(r['evidence']['geometry_recall']['value'], 1)
        s['canonical_dimensions'] = (101, 100)
        r = extended.evaluate([s], artifact(p))
        self.assertIsNone(r['evidence']['geometry_recall']['value'])
        self.assertEqual(r['evidence']['counts']['unsupported_gold_geometry'], 1)

    def test_unlabeled_gold_and_row_reorder_mapping(self):
        s, p = geometry_sample()
        s['labels']['/merchant_name']['status'] = 'unlabeled'
        r = extended.evaluate([s], artifact(p))['evidence']
        self.assertIsNone(r['geometry_recall']['value'])
        s, p = geometry_sample()
        s['gold']['items'] = [row(), row('Vải', '1', 'm', '30', '30')]
        for i in (0, 1):
            for f in COLUMNS:
                s['labels'][f'/items/{i}/{f}'] = {'status': 'present'}
        s['regions']['regions'][0].update(pointer='/items/0/description', text='Trà sen')
        p['payload'] = dict(s['gold'], items=list(reversed(s['gold']['items'])))
        p['field_metadata'][0].update(path='/items/1/description', evidence_text='Trà sen')
        r = extended.evaluate([s], artifact(p))
        self.assertEqual(r['evidence']['geometry_recall']['value'], 1)
        self.assertEqual(r['evidence']['text_e2e_accuracy']['value'], 1)


class ComparisonCalibrationTest(unittest.TestCase):
    def test_comparison_missing_and_mismatched_pins(self):
        a = {k: 'v1' for k in extended.PINS}
        self.assertTrue(extended.compare(dict(B0=a, M0=a, M1=a))['fair'])
        self.assertFalse(extended.compare(dict(B0=a, M0=a))['fair'])
        self.assertFalse(extended.compare(dict(B0=a, M0=a, M1=dict(a, preprocess_version='v2')))['fair'])
        self.assertFalse(extended.compare(dict(B0={}, M0={}, M1={}))['fair'])

    def test_calibration_status_eligibility_and_final_exclusion(self):
        s = table_sample([row()])
        a = artifact(prediction(s))
        a.update({k: 'fixture.v1' for k in extended.PINS})
        a['calibration_protocol_version'] = extended.CALIBRATION_PROTOCOL
        r = extended.evaluate([s], a)
        entries = [e for e in r['correctness_labels'] if e['field'].startswith('/items/')]
        self.assertEqual(len(entries), 5)
        self.assertTrue(all(e['eligible'] and e['correctness'] == 1 for e in entries))
        s['split'] = 'final'
        self.assertFalse(any(e['eligible'] for e in extended.evaluate([s], a)['correctness_labels']))
        s['split'] = 'dev'
        s['gold']['items'].append(row())
        for f in COLUMNS:
            s['labels']['/items/1/' + f] = {'status': 'present'}
        a['predictions'] = [prediction(s)]
        entries = extended.evaluate([s], a)['correctness_labels']
        self.assertFalse(any(e['eligible'] for e in entries if e['field'].startswith('/items/')))

    def test_d32_frozen_errors_hand_counts(self):
        bundle = extended.evaluate_files(ROOT, ROOT / 'tests/fixtures/d12/manifest.json',
            {'fixture': ROOT / 'tests/fixtures/d32-known-predictions.json'})
        r = bundle['reports']['fixture']
        # Receipt: 2 matched rows, one wrong quantity => 9/10 cells, 1 exact.
        # Gold has 6 rows incl failed invoice; missing 1+3=4; 2 extra predictions.
        self.assertEqual(r['tables']['matched_cell_accuracy']['value'], 9/10)
        self.assertEqual(r['tables']['e2e_cell_accuracy']['value'], 9/30)
        self.assertEqual(r['tables']['exact_row_accuracy']['value'], 1/6)
        c = r['tables']['counts']
        self.assertEqual((c['missing_gold_rows'], c['extra_predicted_rows'], c['predicted_duplicates']), (4, 2, 1))
        self.assertEqual(r['accounting']['outcomes'], {'ok': 1, 'failed': 1})
        # 20 receipt + 22 invoice annotated pointers, 22+24 text regions.
        # Only one merchant region supplied: 1/42 coverage, 1/46 geometry recall.
        self.assertEqual(r['evidence']['coverage']['value'], 1/42)
        self.assertEqual(r['evidence']['geometry_recall']['value'], 1/46)
        self.assertEqual(r['evidence']['text_accuracy_on_available']['value'], 1)
        self.assertEqual(r['calibration_coverage']['eligible'], 0)
        self.assertIn('duplicate_predicted_row', [e['category'] for e in r['errors']])

    def test_real_fixture_report_and_cli(self):
        manifest = ROOT / 'tests/fixtures/d12/manifest.json'
        predictions = ROOT / 'tests/fixtures/d31-known-predictions.json'
        bundle = extended.evaluate_files(ROOT, manifest, {'fixture': predictions})
        r = bundle['reports']['fixture']
        # Six rows, 30 annotated cells copied in existing synthetic D3.1 fixture.
        self.assertEqual(r['tables']['counts']['gold_rows'], 6)
        self.assertEqual(r['tables']['matched_cell_accuracy']['numerator'], 30)
        self.assertEqual(r['tables']['exact_row_accuracy']['denominator'], 6)
        self.assertEqual(r['evidence']['coverage']['value'], 0)
        self.assertIsNone(r['evidence']['text_accuracy_on_available']['value'])
        self.assertEqual(r['calibration_coverage']['eligible'], 0)
        self.assertEqual(bundle['comparison']['missing_candidates'], ['B0', 'M0', 'M1'])
        self.assertEqual(bundle['freeze_record']['status'], 'prepared_not_frozen')
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'bundle'
            command = [sys.executable, '-m', 'vietdoc.evaluation', '--root', str(ROOT), '--manifest', str(manifest),
                       '--candidate', 'fixture=' + str(predictions), '--output', str(out)]
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(json.loads((out/'fixture/report.json').read_text()), r)
            labels = [json.loads(line) for line in (out/'fixture/correctness-labels.jsonl').read_text().splitlines()]
            self.assertTrue(all(e['manifest_sha256'] and e['predictions_sha256'] for e in labels))
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
