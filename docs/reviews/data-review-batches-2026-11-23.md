# Duplicate review preparation — 23/11/2026

M05 prepares work while the first batch awaits peer verdict. It does not classify
new pairs, mutate the accepted review, or claim image inspection by a human/AI peer.
[Machine-prepared queue](../../datasets/manifests/d22-review-batches-20261123.json).

Executed from repo root in the pinned Data environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.data.review_batches \
  --root . --manifest datasets/manifests/d22-smoke-v01.json \
  --report datasets/manifests/d22-report-v01.json \
  --review datasets/manifests/d22-duplicate-review-20261122-batch01.json \
  --asset-manifest datasets/processed/d22-smoke-c/manifest.json \
  --output datasets/manifests/d22-review-batches-20261123.json
```

The local asset manifest must match the pinned review manifest byte for byte.
The existing records exporter validates all 80 samples / 480 assets before output:
PNG decoding, path/hash checks, business gold/type, lineage, labels, transcript,
geometry and variant semantics. No renderer replay, OCR or pixel/text QA is claimed.
Both normal and `-O` commands ran and produced identical queue bytes.

Remaining pairs appear once each in eight batches, maximum ten pairs per batch:
33 cross-split (10/10/10/3), then 38 same-split (10/10/10/8). Every base has clean
asset pointers/hashes, lineage, family metadata, row/field/status support. Pair
comparisons are mechanical facts only, never duplicate/independence proof.
Inspection booleans remain false, reviewer/verdict null. Gold and image bytes are
not duplicated into the tracked queue. Source snapshot and review bytes unchanged.

Four focused queue tests PASS: coverage/priority/no implicit verdict, input drift,
invalid asset validation without publication, no-overwrite and bounds. Existing
whole-source exporter tests cover the delegated asset/semantic validation boundary.

Next action: peer/Lead reviews [first ten evidence pairs](data-duplicate-batch01-2026-11-22.md).
Then Data can inspect these prepared batches, record explicit image/content/lineage
findings and version dispositions. Current state remains **10 distinct (AI-assisted
attribution), 71 pending**, no eligible train/dev members. Missing first-batch peer
verdict does not prevent preparing these queues or implementing selection tooling.
