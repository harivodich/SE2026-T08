"""D2 consumer semantics from fresh family renders, including normal/-O probes."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from unittest.mock import patch

from vietdoc.data.generator import d22, integration
from vietdoc.data.generator.templates import families
from vietdoc.data.manifest import encoded, read_json, sha

ROOT = Path(__file__).resolve().parents[2]


class D2SemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        cls.font = integration.resolve_font()
        cls.config = dict(read_json(d22.DEFAULT_CONFIG), font_sha256=sha(cls.font))
        # Every family, with rows that exercise table cells. Keep
        # variant rendering bounded to one base per type; no dataset freeze claim.
        cls.config['rows'] = [3]
        clean_config = dict(cls.config, augmentations=[])
        cls.entries = []
        for config, selected in ((clean_config, None), (cls.config, {'receipt-f00', 'invoice-f06'})):
            records = d22.plan(config, 2202)
            if selected:
                records = [r for r in records if r['family_id'] in selected]
            with patch.object(d22, 'plan', return_value=records):
                for entry, files in d22.generated(ROOT, config, 2202, cls.font):
                    if selected and entry['augmentation']['name'] == 'clean':
                        continue
                    cls.entries.append(entry)
                    for suffix, content in files.items():
                        (cls.base / entry['assets'][suffix]['path']).write_bytes(content)
        cls.data = dict(d22.provenance(ROOT, cls.config, 2202, cls.font), samples=cls.entries)

    def probe(self, data, reason=None):
        path = self.base / 'probe.json'
        path.write_bytes(encoded(data))
        code = ('from pathlib import Path; import sys; '
                'from vietdoc.data.generator.integration import load_artifacts; '
                'list(load_artifacts(Path(sys.argv[1]), Path(sys.argv[2])))')
        for optimized in (False, True):
            with self.subTest(optimized=optimized):
                run = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-c', code,
                                      str(ROOT), str(path)], capture_output=True,
                                     env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')))
                stderr = run.stderr.decode('utf-8')
                self.assertEqual(run.returncode == 0, reason is None, stderr)
                if reason:
                    self.assertIn(reason, stderr)
                    self.assertIn(data['samples'][0]['sample_id'], stderr)

    def test_valid_families_and_quality_variants(self):
        self.assertEqual({e['family_id'] for e in self.entries}, {f['family_id'] for f in families.catalog()})
        self.assertEqual({e['quality'] for e in self.entries}, {'clean', 'bounded', 'content-loss', 'unreadable'})
        # Each D2.2 scalar occurs once, on both sides of the table and in both
        # vocabularies. Table wraps are one logical occurrence, not duplicates.
        for entry in self.entries:
            geometry = read_json(self.base / entry['assets']['regions.json']['path'])
            labels = read_json(self.base / entry['assets']['labels.json']['path'])
            family = next(f for f in families.catalog() if f['family_id'] == entry['family_id'])
            for pointer, label in labels.items():
                hits = integration.occurrences(geometry['regions'], pointer, family['vocabulary'] == 'alternate')
                self.assertEqual(hits, [label['raw']] if label['status'] == 'present' else [])
        self.probe(self.data)

    def test_quality_cannot_be_reclassified(self):
        for entry in self.entries:
            # All four quality categories, both document types and vocabularies.
            if entry['quality'] == 'clean' and entry['family_id'] not in ('receipt-f00', 'invoice-f06'):
                continue
            for quality in ('clean', 'bounded', 'content-loss', 'unreadable', 'typo', None):
                if quality == entry['quality']:
                    continue
                with self.subTest(sample=entry['sample_id'], quality=quality):
                    mutated = dict(entry, quality=quality)
                    self.probe(dict(self.data, samples=[mutated]), 'D2 quality mismatch')
            mutated = dict(entry)
            del mutated['quality']
            self.probe(dict(self.data, samples=[mutated]), 'D2 quality mismatch')

    def test_duplicate_exact_occurrences_by_family(self):
        for entry in self.entries:
            if entry['quality'] != 'clean':
                continue
            for pointer in ('/total_amount', '/merchant_name' if entry['document_type'] == 'receipt' else '/seller_name',
                            '/items/0/description'):
                with self.subTest(family=entry['family_id'], pointer=pointer):
                    geometry_path = self.base / entry['assets']['regions.json']['path']
                    transcript_path = self.base / entry['assets']['txt']['path']
                    geometry_bytes, transcript_bytes = geometry_path.read_bytes(), transcript_path.read_bytes()
                    geometry = read_json(geometry_path)
                    # Copy the complete logical occurrence, including wraps.
                    matching = [r for r in geometry['regions'] if r['pointer'] == pointer]
                    self.assertTrue(matching)
                    # Put the copied occurrence before the page title so even
                    # the last table cell is separated from its original wraps.
                    geometry['regions'] = copy.deepcopy(matching) + geometry['regions']
                    mutated = copy.deepcopy(entry)
                    try:
                        geometry_path.write_bytes(encoded(geometry))
                        transcript_path.write_bytes(''.join(r['text'] + '\n' for r in geometry['regions']).encode('utf-8'))
                        for suffix in ('regions.json', 'txt'):
                            mutated['assets'][suffix]['sha256'] = sha(self.base / mutated['assets'][suffix]['path'])
                        self.probe(dict(self.data, samples=[mutated]), f'occurrence count mismatch: {pointer}')
                    finally:
                        geometry_path.write_bytes(geometry_bytes)
                        transcript_path.write_bytes(transcript_bytes)

    def test_catalog_vocabulary_is_independent_of_index(self):
        family = dict(families.catalog()[0], vocabulary='alternate')
        record = d22.plan(self.config, 2202)[0]
        payload = d22.payload_for(record, read_json(d22.CONFIG))
        _, geometry = families.render_family(payload, family, self.font)
        merchant = next(r for r in geometry['regions'] if r['pointer'] == '/merchant_name')
        self.assertTrue(merchant['text'].startswith(families.ALTERNATE['merchant_name'] + ': '))
        # Exercise the consumer lookup too: the family ID/index still says f00,
        # while the catalog now explicitly selects the alternate vocabulary.
        config = dict(self.config, augmentations=[])
        with tempfile.TemporaryDirectory() as folder, patch.object(d22, 'catalog', return_value=[family]), \
                patch.object(families, 'catalog', return_value=[family]):
            base = Path(folder)
            entries = []
            for entry, files in d22.generated(ROOT, config, 2202, self.font):
                entries.append(entry)
                for suffix, content in files.items():
                    (base / entry['assets'][suffix]['path']).write_bytes(content)
            manifest = base / 'manifest.json'
            manifest.write_bytes(encoded(dict(d22.provenance(ROOT, config, 2202, self.font), samples=entries)))
            self.assertEqual(len(list(integration.load_artifacts(ROOT, manifest))), 1)

    def test_statuses_must_match_variant_semantics(self):
        unreadable = next(e for e in self.entries if e['quality'] == 'unreadable')
        clean = next(e for e in self.entries if e['base_id'] == unreadable['base_id'] and e['quality'] == 'clean')
        mutated = dict(unreadable, assets=clean['assets'], label_statuses=clean['label_statuses'])
        self.probe(dict(self.data, samples=[mutated]), 'D2 unreadable variant has evidence')
        for quality, old, new, reason in (
                ('clean', 'absent', 'obscured', 'D2 clean variant has obscured fields'),
                ('unreadable', 'obscured', 'unlabeled', 'D2 variant has unlabeled fields')):
            entry = next(e for e in self.entries if e['quality'] == quality and
                         old in e['label_statuses'])
            path = self.base / entry['assets']['labels.json']['path']
            original = path.read_bytes()
            labels = read_json(path)
            label = next(v for v in labels.values() if v['status'] == old)
            label['status'] = new
            mutated = copy.deepcopy(entry)
            try:
                path.write_bytes(encoded(labels))
                mutated['assets']['labels.json']['sha256'] = sha(path)
                mutated['label_statuses'] = dict(Counter(v['status'] for v in labels.values()))
                self.probe(dict(self.data, samples=[mutated]), reason)
            finally:
                path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
