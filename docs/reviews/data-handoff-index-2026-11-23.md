# Data handoff index — 23/11/2026

Source verified locally: `3de726a972f4245b1909d80c7584184174ca2ef2`; local commits
await explicit publication. Existing public candidate is [PR88 at 4003df6](https://github.com/harivodich/SE2026-T08/tree/4003df632bd5b50373ac7cf440c4052cb2fed1eb).
Schema/adapter/evaluator bytes are unchanged by M01–M03; only screening, benchmark
guards and tests changed. [Current safe receipt](data-handoff-receipt-2026-11-23.json).

## AI1 full20 / AI2 records

[Existing full20 transfer](https://github.com/user-attachments/files/34526599/full20-transfer.zip),
[original posting](https://github.com/harivodich/SE2026-T08/issues/22#issuecomment-6711644580).
Remote download/access was not rechecked in this execution; existing local transfer
and inner bundle were verified without rerender/repack. Outer transfer hash:
`f3b17ce81d7bb83a2417ab8aa402082c5a304508c7b72756503b13f184b3a84a`.

In the pinned Data environment (Python 3.12.3, Pillow 10.2.0, jsonschema 4.10.3),
from source root, unpack the transfer and substitute new local paths:

```sh
PYTHONPATH=src python3 -B -m vietdoc.data.generator.handoff verify \
  --bundle <folder-containing-inventory-and-d12-handoff.zip> --output <new-root>
PYTHONPATH=src python3 -B -m vietdoc.data.adapters.records \
  --root <new-root> --manifest <new-root>/datasets/manifests/d12-integration-v2.json \
  --full-set --output <new-records.json>
```

Expected: 20 IDs, 10 receipt + 10 invoice, 204 rows, 102 members; manifest
`093b8f772d19e5357ee6209f3358f44d7a072f457aaef64507f38081c0e70e9a`;
records `aca61aaa4da1cbbedcd5e6c4ac3e85d748606cac592f456e78d134c42f725e8f`.
Record counts: 1138 present, 12 absent. Both commands were run against the existing
local bundle into `artifacts/evaluation/data-mini-20261123/full20-verified` and
`full20-records.json`. Handoff regressions: 11 PASS (12.983 s).

AI2 also receives [four-state vectors](data-label-vectors-2026-11-22.json) and
[adapter contract](../label-adapter.md): these cover obscured/unlabeled semantics
not represented by full20. `--full-set` is a D1.2-only check, never a D2 pilot flag.
AI1 native20 and AI2 actual decoded batch/masks remain separate required receipts.

## Evaluator recipe without a private ZIP

An evaluator archive on the Data machine is not an accessible delivery channel.
Recipients can instead use a checkout of the pinned source and its tracked tiny
fictional fixtures. No private `artifacts/evaluation` path or dataset download is
needed. These commands ran after exporting only source/schema/fixtures with
`git archive` to a fresh temporary directory; subprocesses ran from that directory
with `PYTHONPATH` pointing only to its exported `src`:

```sh
PYTHONPATH=src python3 -B -m vietdoc.evaluation --root . \
  --manifest tests/fixtures/d12/manifest.json \
  --predictions tests/fixtures/d31-known-predictions.json --output <new-scalar-dir>
PYTHONPATH=src python3 -B -m vietdoc.evaluation --root . \
  --manifest tests/fixtures/d12/manifest.json \
  --candidate fixture=tests/fixtures/d32-known-predictions.json --output <new-table-dir>
```

Expected independently hand-counted values, rechecked against both outputs:
scalar TP/FP/FN 10/2/2 and EM 10/12; matched cells 9/10; E2E cells 9/30; exact rows
1/6; missing/extra/duplicate rows 4/2/1; outcomes 1 ok + 1 failed; evidence coverage
1/42 and geometry recall 1/46. Calibration eligible=0. These are synthetic oracles,
not actual OCR/extractor scores. The receipt preserves exact expected values.

## Acceptance still owned externally

- AI1: download/verify receipt then native20 requested/attempted/ok/failed/not_run
  with input and engine/profile/model pins; pilot OCR only after membership delivery.
- AI2: reader pointer/status/gold parity and actual target/mask/exclusion evidence;
  actual prediction packets with requested IDs and failures for Data evaluation.
- Lead/peers: first duplicate batch verdict, grouping/support and metric protocol;
  review S0 head and hosted CI before merge, then consumer smoke on merged develop.

No consumer message, upload, approval, Issue closure or GitHub mutation was made.
