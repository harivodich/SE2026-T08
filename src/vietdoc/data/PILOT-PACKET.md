# Non-final pilot input packet

Requires existing Data dependencies and a licensed local Vietnamese font; no
downloads/installations. This command accepts only train/dev families, at most
40 bases/200 variants. D22 keeps its tiny default and optional `family_ids`
config selects existing catalog families without rewriting manifest metadata.

```powershell
$env:PYTHONPATH='src'
python -m vietdoc.data.pilot_packet build --root . --output output/pilot-working --config src/vietdoc/data/generator/d22-pilot-20261126.json --font C:/Windows/Fonts/arial.ttf --seed 20261126 --base-limit 40
python -m vietdoc.data.pilot_packet verify --bundle output/pilot-working/packet --output output/pilot-received
```

Outputs must be fresh. `snapshot/dataset/manifest.json` is the full canonical
manifest for that explicit config; all six assets per member remain referenced.
`snapshot/records.json` uses `vietdoc.training-records.v1` unchanged. Review/plan
retain unresolved candidates and quarantine; packet still ships these real
inputs for development, never as approved training examples.

Archive receiver verifies inventory, archive SHA, every member, portable paths,
casefold aliases, regular-file type, bounds, records/labels/schema, decoded pixels
and grouping before publishing a fresh output root. Pin `transfer.json` SHA256
out of band from the producer handoff before receiving; self-consistent hashes
establish integrity, not producer identity. Exact rerender QA is done in the
producer's pinned renderer environment; receiver requires no producer font.

The checked-in config pins the actual Arial font hash. Use the verified input
archive on another platform; do not silently substitute a font/runtime and call
the resulting bytes the same dataset. A new renderer requires a new snapshot.

For D22, OCR's `--root` is the directory holding the declared PNG paths:

```sh
PYTHONPATH=src python -m vietdoc.pipeline.ocr.handoff --root RECEIVER/dataset --manifest RECEIVER/dataset/manifest.json --output-dir NEW_OCR --model-root LOCAL_OCR_MODELS --max-manifest-samples 160 --artifact-version 2
```

Current token profile is OCR 6784 / input 7424 / output 1280 / sequence 8704;
measure the actual population, especially 30-row cases. Training clearance, consumer
ACK, independent image/content/lineage review and Lead approval stay separate.
