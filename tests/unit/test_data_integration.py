"""D1.2 consumer, coverage, reproducibility and corruption checks."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from vietdoc.data.generator.integration import build, load_artifacts, samples, sha

ROOT = Path(__file__).resolve().parents[2]


class IntegrationDataTest(unittest.TestCase):
    def test_set_coverage(self):
        data = list(samples())
        self.assertEqual(len({s[0] for s in data}), 20)
        self.assertEqual(Counter(s[1] for s in data), {'receipt': 10, 'invoice': 10})
        self.assertEqual(Counter((s[1], s[2]) for s in data),
                         {(k, n): 5 for k in ('receipt', 'invoice') for n in (0, 1)})
        self.assertEqual(Counter(len(s[3]['items']) for s in data), {n: 4 for n in (1, 3, 5, 12, 30)})
        self.assertEqual(data, list(samples()))
        self.assertNotEqual(data, list(samples(1203)))

    def test_tiny_consumer_and_reproduce(self):
        manifest = ROOT / 'tests/fixtures/d12/manifest.json'
        original = list(load_artifacts(ROOT, manifest))
        self.assertEqual(len(original), 2)
        with tempfile.TemporaryDirectory(dir=ROOT / 'datasets/processed') as temp:
            output = Path(temp)
            generated = output / 'manifest.json'
            build(ROOT, output, generated, tiny=True)
            reproduced = list(load_artifacts(ROOT, generated))
            self.assertEqual([g for _, g in original], [g for _, g in reproduced])
            for (first, _), (second, _) in zip(original, reproduced):
                for key in first['assets']:
                    self.assertEqual(first['assets'][key]['sha256'], second['assets'][key]['sha256'])
            with self.assertRaises(FileExistsError):
                build(ROOT, output, generated, tiny=True)
            text = output / 'd12-receipt-03.txt'
            text.write_text('tampered', encoding='utf-8')
            with self.assertRaises(AssertionError):
                list(load_artifacts(ROOT, generated))
            # Even a matching new hash cannot hide transcript/evidence drift.
            data = json.loads(generated.read_text())
            data['samples'][0]['assets']['txt']['sha256'] = sha(text)
            generated.write_text(json.dumps(data))
            with self.assertRaises(AssertionError):
                list(load_artifacts(ROOT, generated))
