"""Versioned producer companion controls; no actual OCR/model measurements."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.evaluation import extended
from vietdoc.evaluation.diagnostics import load

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT/'tests/fixtures/d12/manifest.json'
PREDICTIONS = ROOT/'tests/fixtures/d32-known-predictions.json'


class DiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.artifact = read_json(PREDICTIONS)
        self.ids = {p['sample_id'] for p in self.artifact['predictions']}
        snapshot = dict(page=0, artifact_version=2, recognition_status='partial',
            ocr_version=self.artifact['ocr_version'], preprocess_version=self.artifact.get('preprocess_version'),
            blocks=[dict(block_id='readable', text='Chữ còn đọc được')],
            unreadable_regions=[dict(region_id='obscured-region', reason='EMPTY_RECOGNITION',
                quad=[[.1,.1],[.2,.1],[.2,.2],[.1,.2]], score=0)], review_flags=['OCR_UNREADABLE_REGIONS'])
        self.data = dict(artifact_version='vietdoc.ocr-diagnostics.v1', predictions_sha256=sha(PREDICTIONS),
            dataset_manifest_sha256=self.artifact['dataset_manifest_sha256'],
            ocr_inputs_sha256=self.artifact.get('ocr_inputs_sha256'), samples=[
                dict(sample_id=p['sample_id'], status=p['status'],
                     ocr=deepcopy(snapshot) if p['status']=='ok' else None,
                     **({'error':p['error']} if p['status']=='failed' else {}))
                for p in self.artifact['predictions']])
        self.path = self.base/'diagnostics.json'
        self.save()

    def save(self):
        self.path.write_bytes(encoded(self.data))

    def read(self):
        return load(self.path, self.artifact, sha(PREDICTIONS), self.ids)

    def test_partial_failed_records_preserved_without_changing_scores(self):
        plain = extended.evaluate_files(ROOT, MANIFEST, {'fixture':PREDICTIONS})
        with_diagnostics = extended.evaluate_files(ROOT, MANIFEST, {'fixture':PREDICTIONS},
                                                 diagnostics_paths={'fixture':self.path})
        a, b = plain['reports']['fixture'], with_diagnostics['reports']['fixture']
        for metric in ('scalar', 'ocr', 'tables', 'evidence', 'calibration_coverage', 'accounting'):
            self.assertEqual(a[metric], b[metric])
        result = b['ocr_diagnostics']
        self.assertEqual(result['samples'], self.data['samples'])
        self.assertEqual(result['known_id_recognition_status_counts'], {'partial':1})
        self.assertEqual(result['known_id_snapshot_outcomes'], {'ok':1, 'unavailable':1})
        self.assertEqual(b['inputs']['diagnostics_sha256'], sha(self.path))
        self.assertEqual(with_diagnostics['freeze_record']['diagnostics'], {'fixture':sha(self.path)})

    def test_hash_version_id_and_status_corruption_rejected(self):
        original = deepcopy(self.data)
        for case, reason in (('predictions_sha256','prediction hash mismatch'),
                             ('dataset_manifest_sha256','dataset hash mismatch'),
                             ('ocr_inputs_sha256','OCR input hash mismatch'),
                             ('artifact_version','unsupported OCR diagnostics'),
                             ('duplicate','duplicate/unknown diagnostics'), ('missing','missing diagnostics IDs'),
                             ('status','diagnostics outcome mismatch'), ('recognition','inconsistent recognition status'),
                             ('version','diagnostics version mismatch')):
            self.data = deepcopy(original)
            if case=='duplicate':
                self.data['samples'].append(deepcopy(self.data['samples'][0]))
            elif case=='missing':
                self.data['samples'].pop()
            elif case=='status':
                self.data['samples'][0]['status']='failed'
            elif case=='recognition':
                self.data['samples'][0]['ocr']['recognition_status']='complete'
            elif case=='version':
                self.data['samples'][0]['ocr']['ocr_version']='wrong'
            else:
                self.data[case]='wrong'
            self.save()
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, reason):
                self.read()

    def test_unreadable_and_failed_partial_snapshots_keep_original_status(self):
        self.data['samples'][0]['ocr'].update(blocks=[], recognition_status='unreadable')
        self.save()
        result = self.read()
        self.assertEqual(result['known_id_recognition_status_counts'], {'unreadable':1})
        self.assertEqual(result['known_id_snapshot_outcomes'], {'ok':1, 'unavailable':1})
        self.data['samples'][1]['ocr'] = deepcopy(self.data['samples'][0]['ocr'])
        self.data['samples'][1]['ocr'].update(blocks=[dict(block_id='readable', text='Chữ')],
                                            recognition_status='partial')
        self.save()
        result = self.read()
        self.assertEqual(result['known_id_recognition_status_counts'], {'unreadable':1, 'partial':1})
        self.assertEqual(result['known_id_snapshot_outcomes'], {'ok':1, 'failed':1})
        self.assertEqual(result['samples'][1]['error'], self.data['samples'][1]['error'])

    def test_unknown_predictions_remain_integrity_issues_not_support(self):
        entry = deepcopy(self.data['samples'][0])
        entry['sample_id']='unknown'
        self.data['samples'].append(entry)
        self.artifact['predictions'].append(dict(self.artifact['predictions'][0], sample_id='unknown'))
        self.save()
        result = self.read()
        self.assertEqual(result['unknown_ids'], ['unknown'])
        self.assertEqual(result['known_id_recognition_status_counts'], {'partial':1})
        self.artifact['predictions'].append(self.artifact['predictions'][0])
        result = self.read()
        self.assertEqual(result['unassociated_duplicate_prediction_ids'], ['d12-receipt-03'])
        self.assertEqual(result['known_id_recognition_status_counts'], {})
        self.assertEqual(result['known_id_snapshot_outcomes'], {'duplicate':1, 'unavailable':1})

    def test_duplicate_prediction_keeps_e2e_accounting_with_companion(self):
        artifact = deepcopy(self.artifact)
        artifact['predictions'].append(deepcopy(artifact['predictions'][0]))
        predictions = self.base/'predictions.json'
        predictions.write_bytes(encoded(artifact))
        self.data['predictions_sha256'] = sha(predictions)
        self.save()
        report = extended.evaluate_files(ROOT, MANIFEST, {'fixture':predictions},
            diagnostics_paths={'fixture':self.path})['reports']['fixture']
        self.assertEqual(report['accounting']['outcomes'], {'duplicate':1, 'failed':1})
        self.assertEqual(report['tables']['e2e_cell_accuracy']['value'], 0)
        self.assertEqual(report['ocr_diagnostics']['known_id_snapshot_outcomes'], {'duplicate':1, 'unavailable':1})

    def test_cli_normal_and_optimized(self):
        for optimized in (False, True):
            output = self.base/str(optimized)
            run = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-m',
                'vietdoc.evaluation','--root',str(ROOT),'--manifest',str(MANIFEST),
                '--candidate','fixture='+str(PREDICTIONS),'--diagnostics','fixture='+str(self.path),
                '--output',str(output)], capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr.decode())
            self.assertEqual(read_json(output/'fixture/report.json')['ocr_diagnostics']['samples'], self.data['samples'])


if __name__=='__main__':
    unittest.main()
