"""Run: python -m vietdoc.evaluation --help."""
import argparse
import json
from pathlib import Path

from .scalar_ocr import evaluate_files, markdown


def main():
    parser = argparse.ArgumentParser(description='Offline scalar/OCR evaluator (no inference)')
    parser.add_argument('--root', type=Path, required=True, help='asset root (D1.2: repository root)')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--predictions', type=Path)
    parser.add_argument('--candidate', action='append', default=[], metavar='NAME=PATH',
                        help='D3.2 mode; repeat for B0/M0/M1 or fixture; cannot combine --predictions')
    parser.add_argument('--output', type=Path, required=True, help='new output directory; never overwritten')
    args = parser.parse_args()
    if args.candidate:
        from .extended import evaluate_files as extended_files, write_bundle
        import re
        candidates = {}
        for value in args.candidate:
            name, sep, path = value.partition('=')
            if not sep or not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in candidates:
                parser.error('candidate must be unique safe NAME=PATH')
            candidates[name] = Path(path)
        if args.predictions:
            parser.error('use --candidate OR --predictions')
        write_bundle(extended_files(args.root, args.manifest, candidates), args.output)
        return
    if args.predictions is None:
        parser.error('--predictions or --candidate required')
    report = evaluate_files(args.root, args.manifest, args.predictions)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                     allow_nan=False) + '\n', encoding='utf-8')
    (args.output / 'report.md').write_text(markdown(report), encoding='utf-8')


if __name__ == '__main__':
    main()
