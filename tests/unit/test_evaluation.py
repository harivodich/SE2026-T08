"""Hand-computed D3.1 oracles. All predictions here are synthetic test inputs."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unicodedata

from vietdoc.data.manifest import sha
from vietdoc.evaluation.policy import FIELDS, normalize
from vietdoc.evaluation.scalar_ocr import evaluate, evaluate_files, load_gold, markdown

ROOT = Path(__file__).resolve().parents[2]


def sample(sid='r', kind='receipt', values=None, statuses=None, transcript='a b'):
    values = values or {'merchant_name': 'Cửa Hàng', 'total_amount': '45000'}
    gold = dict.fromkeys(FIELDS[kind])
    gold.update(values)
    labels = {'/' + k: {'status': 'present' if v is not None else 'absent'} for k, v in gold.items()}
    for key, value in (statuses or {}).items():
        labels['/' + key] = {'status': value}
    return dict(sample_id=sid, document_type=kind, gold=gold, labels=labels,
                transcript=transcript, transcript_scope='full_page')


def prediction(s, **changes):
    record = dict(sample_id=s['sample_id'], status='ok', payload=deepcopy(s['gold']),
                  ocr_text=s['transcript'])
    record.update(changes)
    return record


def artifact(*records):
    return dict(artifact_version='vietdoc.predictions.v1', model_version='fixture-only.v1',
                normalizer_version='fixture-canonical.v1', ocr_version='fixture-only.v1',
                predictions=list(records))


class EvaluationTest(unittest.TestCase):
    def test_all_correct_and_type_critical_slices(self):
        r = sample(values={'transaction_date': '2026-10-25', 'total_amount': '45000'})
        i = sample('i', 'invoice', {'issue_date': '2026-10-24', 'total_amount': '12000'})
        report = evaluate([r, i], artifact(prediction(i), prediction(r)))  # match IDs, not order
        for group in ('all', 'receipt', 'invoice', 'critical/date', 'critical/total'):
            metrics = report['scalar'][group]
            for name in ('normalized_exact_match', 'precision', 'recall', 'f1'):
                self.assertEqual(metrics[name]['value'], 1)
            self.assertEqual(metrics['counts']['fp'], 0)
        self.assertEqual(report['scalar']['all']['normalized_exact_match']['denominator'], 4)
        self.assertEqual(report['scalar']['all']['counts']['absent'], 9)
        self.assertEqual(report['ocr']['all']['cer']['numerator'], 0)
        self.assertEqual(report['ocr']['all']['cer']['denominator'], 6)

    def test_wrong_value_counts_fp_and_fn(self):
        s = sample()
        p = prediction(s)
        p['payload']['merchant_name'] = 'Sai'
        result = evaluate([s], artifact(p))
        metrics = result['scalar']['all']
        self.assertEqual((metrics['counts']['tp'], metrics['counts']['fp'], metrics['counts']['fn']), (1, 1, 1))
        for key in ('normalized_exact_match', 'precision', 'recall', 'f1'):
            self.assertEqual(metrics[key]['value'], 0.5)
        self.assertEqual(result['errors'][0]['category'], 'wrong_value')

    def test_present_null_missing_and_empty(self):
        for value, category in ((None, 'present_null'), ('  ', 'present_empty'), ('MISSING', 'present_missing')):
            with self.subTest(category=category):
                s = sample()
                p = prediction(s)
                if value == 'MISSING':
                    del p['payload']['merchant_name']
                else:
                    p['payload']['merchant_name'] = value
                result = evaluate([s], artifact(p))['scalar']['all']
                self.assertEqual(result['counts'][category], 1)
                self.assertEqual(result['precision']['value'], 1)
                self.assertEqual(result['recall']['value'], 0.5)
                self.assertEqual(result['f1']['numerator'], 2)
                self.assertEqual(result['f1']['denominator'], 3)

    def test_absent_false_fill_does_not_inflate_em(self):
        s = sample()
        p = prediction(s)
        p['payload']['merchant_address'] = 'Địa chỉ bịa'
        result = evaluate([s], artifact(p))['scalar']['all']
        self.assertEqual(result['counts']['false_fill'], 1)
        self.assertEqual(result['normalized_exact_match']['value'], 1)
        self.assertEqual(result['precision']['value'], 2/3)
        self.assertEqual(result['recall']['value'], 1)
        self.assertEqual(result['f1']['value'], 4/5)
        absent = sample(values={'merchant_name': None, 'total_amount': None})
        result = evaluate([absent], artifact(prediction(absent)))['scalar']['all']
        self.assertIsNone(result['normalized_exact_match']['value'])
        self.assertIsNone(result['f1']['value'])
        self.assertEqual(result['counts']['tp'], 0)

    def test_unlabeled_obscured_and_implicit_unlabeled(self):
        s = sample(statuses={'merchant_name': 'unlabeled', 'total_amount': 'obscured'})
        del s['labels']['/transaction_date']
        p = prediction(s)
        p['payload'].update(merchant_name='Bịa', total_amount='sai', transaction_date='sai')
        result = evaluate([s], artifact(p))['scalar']['all']
        self.assertEqual(result['normalized_exact_match']['support'], 0)
        self.assertEqual(result['normalized_exact_match']['exclusions'], {'unlabeled': 2, 'obscured': 1})
        for key in ('normalized_exact_match', 'precision', 'recall', 'f1'):
            self.assertIsNone(result[key]['value'])
        self.assertEqual(result['counts']['fp'], 0)

    def test_normalization_proposal_boundaries(self):
        self.assertEqual(normalize('merchant_name', unicodedata.normalize('NFD', ' Cửa\n Hàng ')), 'Cửa Hàng')
        self.assertNotEqual(normalize('merchant_name', 'Cửa'), normalize('merchant_name', 'Cua'))
        self.assertNotEqual(normalize('merchant_name', 'Cửa'), normalize('merchant_name', 'cửa'))
        self.assertIsNone(normalize('merchant_name', '\t\n'))
        self.assertEqual(normalize('total_amount', '45000.00'), normalize('total_amount', '45000'))
        # Canonical decimal 45.000 means 45, never locale guessing 45000.
        self.assertEqual(normalize('total_amount', '45.000'), 45)
        self.assertNotEqual(normalize('total_amount', '45.000'), normalize('total_amount', '45000'))
        self.assertEqual(normalize('issue_date', '2024-02-29'), '2024-02-29')
        for field, value in (('issue_date', '29/02/2024'), ('issue_date', '2025-02-29'),
                             ('issue_date', '2026-1-01'), ('total_amount', '45.000 đ'),
                             ('total_amount', '45,00'), ('total_amount', 45000.0),
                             ('total_amount', '-1'), ('transaction_time', '25:00')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(field, value)

    def test_invalid_prediction_value_cannot_match(self):
        s = sample()
        p = prediction(s)
        p['payload']['total_amount'] = '45.000 đ'
        result = evaluate([s], artifact(p))
        self.assertEqual(result['scalar']['all']['counts']['invalid_value'], 1)
        self.assertEqual(result['scalar']['all']['f1']['value'], .5)
        p['payload']['total_amount'] = '45000.00'
        p['payload']['merchant_name'] = unicodedata.normalize('NFD', ' Cửa\n Hàng ')
        self.assertEqual(evaluate([s], artifact(p))['scalar']['all']['f1']['value'], 1)

    def test_frozen_known_score_fixture(self):
        report = evaluate_files(ROOT, ROOT / 'tests/fixtures/d12/manifest.json',
                                ROOT / 'tests/fixtures/d31-known-predictions.json')
        result = report['scalar']['all']
        # 12 present gold, receipt wrong name + null total => 10 TP, 2 FN.
        # Wrong name + invoice absent buyer false fill => 2 FP.
        self.assertEqual((result['counts']['tp'], result['counts']['fp'], result['counts']['fn']), (10, 2, 2))
        self.assertEqual(result['normalized_exact_match']['value'], 10/12)
        self.assertEqual(result['f1']['value'], 20/24)
        self.assertEqual(report['scalar']['receipt']['recall']['value'], 3/5)
        self.assertEqual(report['scalar']['invoice']['precision']['value'], 7/8)
        self.assertEqual(report['scalar']['critical/total']['recall']['value'], 1/2)
        self.assertEqual(report['ocr']['all']['cer']['value'], 0)
        self.assertEqual(report['ocr']['all']['wer']['value'], 0)

    def test_missing_failed_duplicate_unknown_retained(self):
        samples = [sample(x) for x in ('missing', 'failed', 'duplicate')]
        failed = prediction(samples[1], status='failed', error='engine crashed')
        duplicate = prediction(samples[2])
        unknown = dict(duplicate, sample_id='unknown')
        result = evaluate(samples, artifact(failed, duplicate, duplicate, unknown))
        self.assertEqual(result['accounting']['outcomes'], {'missing': 1, 'failed': 1, 'duplicate': 1})
        self.assertEqual(result['accounting']['unknown_ids'], ['unknown'])
        self.assertEqual(result['scalar']['all']['counts']['fn'], 6)
        self.assertEqual(result['scalar']['all']['normalized_exact_match']['denominator'], 6)
        self.assertEqual(result['scalar']['all']['f1']['value'], 0)
        self.assertEqual(result['ocr']['all']['cer']['value'], 1)
        self.assertEqual(result['ocr']['all']['wer']['value'], 1)
        self.assertEqual(len(result['samples']), 3)
        self.assertEqual(result['samples'][1]['reason'], 'engine crashed')
        self.assertIn('duplicate_prediction_id', [e['category'] for e in result['issues']])

    def test_invalid_record_and_missing_ocr(self):
        s = sample()
        for changes in ({'status': 'bogus'}, {'payload': []}, {'payload': {'unexpected': 'x'}}, {'ocr_text': 42}):
            with self.subTest(changes=changes):
                result = evaluate([s], artifact(prediction(s, **changes)))
                self.assertEqual(result['accounting']['outcomes'], {'invalid': 1})
                self.assertEqual(result['scalar']['all']['recall']['value'], 0)
        p = prediction(s)
        del p['ocr_text']
        result = evaluate([s], artifact(p))
        self.assertEqual(result['ocr']['all']['counts']['missing_or_failed_ocr'], 1)
        self.assertEqual(result['ocr']['all']['wer']['numerator'], 2)

    def test_ocr_hand_calculated_insert_delete_substitute(self):
        # ref a b: 3 chars / 2 words. Independent one-edit cases, each = one edit.
        for predicted, ce, we in (('a bx', 1, 1), ('a ', 2, 1), ('a c', 1, 1)):
            with self.subTest(predicted=predicted):
                s = sample()
                result = evaluate([s], artifact(prediction(s, ocr_text=predicted)))['ocr']['all']
                self.assertEqual(result['cer']['numerator'], ce)
                self.assertEqual(result['cer']['denominator'], 3)
                self.assertEqual(result['wer']['numerator'], we)
                self.assertEqual(result['wer']['denominator'], 2)
        # Corpus rate, not mean of sample rates: 1 edit / (3+1) chars.
        a, b = sample(), sample('b', transcript='x')
        result = evaluate([a, b], artifact(prediction(a, ocr_text='a c'), prediction(b)))
        self.assertEqual(result['ocr']['all']['cer']['value'], 1/4)
        self.assertEqual(result['ocr']['all']['wer']['value'], 1/3)

    def test_empty_transcript_scope_and_unicode(self):
        for predicted, numerator in (('', 0), ('x', 1)):
            s = sample(transcript='')
            result = evaluate([s], artifact(prediction(s, ocr_text=predicted)))['ocr']['all']
            for key in ('cer', 'wer'):
                self.assertIsNone(result[key]['value'])
                self.assertEqual(result[key]['numerator'], numerator)
                self.assertEqual(result[key]['support'], 1)
        s = sample(transcript='Cửa hàng')
        result = evaluate([s], artifact(prediction(s, ocr_text=unicodedata.normalize('NFD', ' Cửa\n hàng '))))
        self.assertEqual(result['ocr']['all']['cer']['value'], 0)
        for scope, transcript in (('qa_answers', 'a b'), ('full_page', None), (None, 'a b')):
            s = sample(transcript=transcript)
            s['transcript_scope'] = scope
            result = evaluate([s], artifact(prediction(s)))['ocr']['all']
            self.assertEqual(result['cer']['support'], 0)
            self.assertEqual(result['cer']['exclusions'], {'no_full_page_gold': 1})

    def test_empty_set_and_bad_gold(self):
        result = evaluate([], artifact())
        self.assertIsNone(result['scalar']['invoice']['f1']['value'])
        s = sample()
        with self.assertRaisesRegex(ValueError, 'duplicate gold'):
            evaluate([s, s], artifact())
        s['labels']['/merchant_name']['status'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'inconsistent gold'):
            evaluate([s], artifact())

    def test_d12_artifact_pins_cli_and_tampering(self):
        manifest = ROOT / 'tests/fixtures/d12/manifest.json'
        _, samples, pins = load_gold(ROOT, manifest)
        self.assertEqual(len(samples), 2)
        self.assertEqual(len(pins), 6)
        # Empty fixture predictions exercise failure accounting, never a model result.
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            p = base / 'predictions.json'
            data = artifact()
            data['dataset_manifest_sha256'] = sha(manifest)
            p.write_text(json.dumps(data), encoding='utf-8')
            result = evaluate_files(ROOT, manifest, p)
            self.assertEqual(result['scalar']['all']['counts']['present'], 12)
            self.assertEqual(result['scalar']['all']['counts']['absent'], 1)
            self.assertEqual(result['accounting']['outcomes'], {'missing': 2})
            self.assertEqual(result['inputs']['manifest_sha256'], sha(manifest))
            self.assertIn('present_missing', markdown(result))
            command = [sys.executable, '-m', 'vietdoc.evaluation', '--root', str(ROOT),
                       '--manifest', str(manifest), '--predictions', str(p), '--output', str(base / 'report')]
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(json.loads((base / 'report/report.json').read_text()), result)
            self.assertTrue((base / 'report/report.md').is_file())
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            data['dataset_manifest_sha256'] = 'bad'
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'pin mismatch'):
                evaluate_files(ROOT, manifest, p)
            altered = json.loads(manifest.read_text())
            altered['samples'][0]['assets']['gold.json']['sha256'] = 'bad'
            m = base / 'manifest.json'
            m.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                load_gold(ROOT, m)
            altered['samples'][0]['assets']['gold.json']['path'] = '../outside.json'
            m.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'invalid relative path'):
                load_gold(ROOT, m)


if __name__ == '__main__':
    unittest.main()
