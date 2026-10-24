"""Run: python -m vietdoc.evaluation --help."""
import argparse
import json
from pathlib import Path

from .scalar_ocr import evaluate_files, markdown


def main():
    parser = argparse.ArgumentParser(description='Offline scalar/OCR evaluator (no inference)')
    parser.add_argument('--root', type=Path, required=True, help='asset root (D1.2: repository root)')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new output directory; never overwritten')
    args = parser.parse_args()
    report = evaluate_files(args.root, args.manifest, args.predictions)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                     allow_nan=False) + '\n', encoding='utf-8')
    (args.output / 'report.md').write_text(markdown(report), encoding='utf-8')


if __name__ == '__main__':
    main()
