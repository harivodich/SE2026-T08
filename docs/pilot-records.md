# Pilot selected-record preparation — Data companion v1

Owner Data; consumer review AI1/AI2 and membership/support acceptance Lead.
This adds an offline preparation tool, not an approved pilot, shared schema change,
new training format, archive publication or validation bypass.

```sh
PYTHONPATH=src python3 -B -m vietdoc.data.pilot_records --root . \
  --manifest <pinned-source-manifest> --report <pinned-report> \
  --review <versioned-review> --plan <recomputed-plan> \
  --asset-manifest <byte-identical-manifest-beside-local-assets> \
  --output <new-preparation.json>
```

The source is exposed, non-frozen D2.2 smoke only. `plan_files` recomputes the plan
from hash-bound manifest/report/review. Every plan field must match, so hand-edited
member lists, aliased/unknown IDs, dropped variants or cross-split assignments
cannot override it. Both receipt/invoice × train/dev cells must have support.
The source manifest is never cut or rewritten to manufacture a canonical subset.

The existing `training_packet` validates **all** source members/assets before any
selection; corruption in an excluded/final member also rejects preparation. The
local asset manifest must match the pinned source bytes. Whole-file pins are
rechecked after validation; failure does not publish output or create its parent.
Existing output is never overwritten, in normal or optimized Python.

The output is a new `vietdoc.pilot-records-preparation.v1` envelope containing:

- `inputs`: names/hashes of manifest, report, review, plan and local asset manifest.
- `selection`: exact train/dev members, after-counts and selected group/component
  decisions from the recomputed plan. All eligible group members/variants remain.
- `training_records`: unchanged `vietdoc.training-records.v1` shape and status/value
  meanings, filtered records and recomputed counts. No historical final record,
  gold or label payload is exported. Source pins remain the **full** source pins.
- `status=prepared_not_approved` and prerequisites: membership/support acceptance,
  asset/gold/pixel QA, archive verification, AI1 OCR and AI2 actual reader ACK.

Asset references still resolve relative to the **original local asset manifest**
directory; the JSON does not embed images or promise a portable archive. A receiver
must use the same validated source/selection, not treat the filtered packet as a
new full D2.2 manifest. This artifact remains internal preparation until membership
is accepted; it must not be presented as training clearance. Actual packaging must
copy only accepted selected assets, preserve/hash their paths, verify from a fresh
root and avoid distributing raw final assets. Archive delivery and receiver ACK
are separate R03/R04 acceptance mini tasks.

Current historical snapshot has 71 pending pairs and zero support. The tool rejects
it without output; that is correct behavior, not pilot completion. Positive tests
use freshly rendered tiny fictional data with explicitly fictional dispositions;
they are source-boundary tests, never a replacement peer verdict on actual data.
