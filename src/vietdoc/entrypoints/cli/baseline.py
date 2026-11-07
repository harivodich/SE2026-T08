"""Offline B0 predictions; no model downloads, business DB or public API calls."""

import argparse
import json
from pathlib import Path

from vietdoc.pipeline.extraction.ocr_input import BaselineError
from vietdoc.pipeline.extraction.predictions import export_predictions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory, never overwritten")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--renderer-fixtures", action="store_true", help="Explicit simulated OCR from D1 renderer text/boxes")
    mode.add_argument("--ocr-inputs", type=Path, help="Hash-pinned OCR/PreparedPage input manifest")
    args = parser.parse_args(argv)
    try:
        artifact = export_predictions(args.root, args.manifest, args.output,
                                      ocr_inputs=args.ocr_inputs, renderer_fixtures=args.renderer_fixtures)
    except (BaselineError, OSError) as error:
        parser.exit(2, f"Baseline export failed: {error.code if isinstance(error, BaselineError) else type(error).__name__}\n")
    counts = {status: sum(record["status"] == status for record in artifact["predictions"]) for status in ("ok", "failed")}
    print(json.dumps(dict(**counts, artifact=str(args.output / "predictions.json"), input_mode=artifact["input_mode"])))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
