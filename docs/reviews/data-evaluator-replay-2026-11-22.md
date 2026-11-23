# #35/#37/#43 — evaluator replay packet, 22/11/2026

Mini tasks F1/F2. Reuses accepted #14 evaluator source; normalization, matching,
calibration and final protocol retain their existing Proposed status.

Actual commands from repo root in the existing Data environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover \
  -s tests/unit -p 'test_evaluation*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.evaluation \
  --root . --manifest tests/fixtures/d12/manifest.json \
  --predictions tests/fixtures/d31-known-predictions.json \
  --output artifacts/evaluation/data-increments-20261122/scalar
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.evaluation \
  --root . --manifest tests/fixtures/d12/manifest.json \
  --candidate fixture=tests/fixtures/d32-known-predictions.json \
  --output artifacts/evaluation/data-increments-20261122/table
```

49 evaluator tests PASS (12.960 s), both CLI commands exit 0. Oracles cover scalar
wrong/missing/false-fill, four statuses, Unicode/whitespace, reorder/wrap/duplicate/
missing/unmatched/empty rows, evidence support and failed/missing accounting.

## Relocated packet replay

Local ignored archive:
`artifacts/evaluation/data-increments-20261122/evaluator-replay-20261122.zip`.
Contains Data/evaluator source/configs, business schema, two tiny fictional D1
samples, synthetic prediction fixtures, policy/runbook, `replay.py` and member
hash index. [Safe archive/member pins and expected values](data-evaluator-replay-2026-11-22.json)
are tracked; no full dataset/model/weights are in this packet.

Unpack into a new folder and run from it with the existing Data environment:

```sh
python3 -B replay.py --output /path/to/new-replay-output
```

This exact script was run after extracting a copy under a fresh `/tmp` directory,
with subprocess working directory `/tmp` and `PYTHONPATH` set to the relocated
packet source. Exit 0. Member hashes and independent expected numerator/denominator
values matched; no checkout assets/import fallback or rerender were required.

| Hand-counted result | Actual |
|---|---|
| Scalar TP / FP / FN; EM | 10 / 2 / 2; 10/12 |
| Table matched cells / E2E cells / exact rows | 9/10; 9/30; 1/6 |
| Missing / extra / duplicate rows | 4 / 2 / 1 |
| Prediction outcomes | 1 ok, 1 failed; failed invoice retained |
| Evidence field coverage / geometry recall | 1/42; 1/46 |
| Calibration eligible | 0 |

Archive SHA-256 `782f24a5d09fb21f13ba3c274799590c85de5b162ab6e53a7e793d1305230955`,
347021 bytes. Packet index pins 69 files plus the index itself in the archive;
script hashes are included. Logs/reports stay in ignored evaluation artifacts.

This is Data replay, not AI1/AI2 ACK, actual OCR/model quality or calibration
readiness. Output freeze record remains `prepared_not_frozen`. Recipients should
record packet hash, versions, command, scores and disagreements by sample/path.
Actual AI1 OCR and AI2 prediction packets/pins are still required for F3; Lead
acceptance at #53 is still required for F4. No final data was opened or scored.
