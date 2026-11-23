# #38 — first cross-split inspection batch, 22/11/2026

Mini tasks D1/D2 in [execution ledger](data-increments-2026-11-22.md).
Attribution: **Codex AI-assisted image/content/lineage inspection**, not human
sign-off, AI1/AI2 consumer ACK or Lead approval. No grouping/split change.

## Inputs and actual inspection

Rechecked the #85 historical snapshot at `datasets/processed/d22-smoke-c`:
480/480 unique asset paths/hash matches, 80 samples, 20 clean bases; local
manifest/report byte hashes match the tracked pinned inputs. Recomputed leakage
screening matches historical report. This set was already exposed integration
smoke, including IDs named final; `final_frozen=false`. It is not a new final set.

Inspected original full-resolution PNGs for receipt f00/f02/f03/f04 and lossless
content crops of receipt f05/f06/f07 and invoice f00/f01/f05/f06/f07/f09. Crops
remove only bottom white margin, not text, and were saved outside the snapshot.
Read gold/transcript/labels/regions and family/source/base/assignment lineage
from the exact hashed clean samples. No augmentation variants or predictions
were used as evidence. This is duplicate inspection, not exhaustive annotation QA.

## Versioned outputs

- [Per-pair evidence](../../datasets/manifests/d22-pair-evidence-20261122-batch01.json):
  queue/manifest/report/catalog pins, exact six-asset references, lineage, observed
  layout/content and a reason for each of the ten candidate IDs.
- [New review snapshot](../../datasets/manifests/d22-duplicate-review-20261122-batch01.json):
  retains all 81 IDs; first ten classified distinct after inspection, 71 pending
  (33 cross-split + 38 same-split). Historical all-pending file is unchanged.

The distinct decisions follow visible differences in document type/scalar
structure, header/totals placement, column order and independently generated
business content/lineage. For example, receipt f00 versus receipt f06 has stacked
standard header/totals below/empty table versus two-column alternate header/totals
above/one row, with different date/time/amount. Receipt f03 versus f07 has 12
versus 3 rows and different header/totals/column order. Receipt f04 versus invoice
f09 both have 30 unit-first rows, but different document scalar structure,
identities/values and stacked/two-column header/totals placement.

Different hashes or low content overlap alone were not used as proof. Shared
fictional names and reuse of the generator still limit statistical independence;
these decisions do not establish independent mock layouts or quality support.

## Verification and next gate

Actual command from repo root in the existing Data environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.data.duplicate_review \
  --manifest datasets/manifests/d22-smoke-v01.json \
  --report datasets/manifests/d22-report-v01.json \
  --review datasets/manifests/d22-duplicate-review-20261122-batch01.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover \
  -s tests/unit -p test_data_duplicate_review.py -v
```

Exit 0; 10 distinct + 71 pending; `review_complete=false`, `unresolved=71`;
8 regression tests PASS. Peer must replay the pinned evidence and accept or
challenge the first batch before the remaining batches proceed under this plan.
No confirmed wrong grouping has been found in this batch, so there is no invented
grouping fix/regression. D3/D4 remain pending peer/Lead input. Nothing was posted
to GitHub and no reviewers were messaged in this run.
