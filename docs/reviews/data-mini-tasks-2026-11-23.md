# Data mini tasks — 23/11/2026

User authorized implementation and separate local commits, not push/merge or
messages to consumers. Starting head: `4003df632bd5b50373ac7cf440c4052cb2fed1eb`,
branch `feature/SE-22_data_handoff_increments`; develop is `e040e94`.
The two user-supplied PR88 review/plan files are inputs, preserved untracked.
This execution ledger supplements the current plan, not a new roadmap or approval.

## Executable increments

Fix and regression belong in the same commit. Record commands/results below as
they actually run. LOCAL PASS never means hosted CI, peer acceptance or model quality.

| ID | Plan | Mini task / concrete completion criterion | Initial status |
|---|---|---|---|
| M00 | All | Decompose work, preserve existing files, identify real dependencies | This ledger |
| M01 | S0 | Reject missing/duplicate clean representatives; rebound-hash file/CLI regressions; valid baseline unchanged | Ready |
| M02 | R00 | Separate fresh-output full-set rejection from no-overwrite, normal/-O; mutation detects dropped flag | Ready |
| M03 | R00 | Derive benchmark bound from actual workload; reject forged/malformed counters before stage work | Ready |
| M04 | R01/R05 | Recheck existing transfer locally; source-based evaluator replay recipe and handoff index with exact pins/counts | Ready; receiver ACK separate |
| M05 | R02 | Prepare next duplicate-review batches with pinned clean assets/content/lineage and cross-split priority; no implicit peer verdict | Ready; accepted dispositions await peer |
| M06 | R03 | Implement selection-to-records preparation against validated source and recomputed plan; reject tampering, partial groups, invalid IDs and zero support | Ready for tooling; actual membership blocked |
| M07 | All | Run affected suites, inspect complete diff and record source/commands/limits and remaining owner-specific work | After M01–M06 |

## Remaining acceptance mini tasks

These are concrete next units, not automatically completed by source commits.
No empty commit is needed for an external receipt or decision.

| Plan | Mini task / output | Required input and owner | Work Data can continue |
|---|---|---|---|
| R01 | Consumer download/verify receipt; smoke merged develop; old PR disposition | AI1/AI2 receipts; Lead merge/coverage decision | M04, evaluator recipes |
| R02 | Peer verdict on first ten pairs; inspect/review subsequent batches; version dispositions; recompute groups and support | AI1/AI2/Lead first-batch verdict and grouping acceptance | M05 draft evidence, asset/content checks |
| R03 | QA accepted clean/variants; publish train/dev archive; fresh-root replay | Accepted membership/support, Lead; allocated storage/access | M06 preparation code and negative controls |
| R04 | Check decoded reader/status/masks by pointer; resolve overflow/filter proposal | Actual batch/tokenizer evidence, AI2 | Existing four-state vectors and Data adapter checks |
| R05 | Join pilot OCR IDs/hashes; validate actual packets; evaluate baseline and per-ID failures | Pilot OCR cache, AI1; predictions and profile pins, AI2 | Known-score replay and packet preflight |
| R06a | Review C01–C06 oracles, support/targets and consumer semantics | AI1/AI2 review; Lead protocol decision | Draft protocol and reproducible oracles |
| R06b | Compare B0/M0/M1 on identical dev population and report missing candidates | Actual complete candidate packets, AI2 | Dataset/QA preparation without inventing scores |
| R07 | Propose volume/family support; generate/version accepted batches; exposure ledger and split audit | Actual G0 capacity, AI2; target/support decision, Lead | Audit current exposure and draft batch scope |
| R08 | Obtain independent layout sketches; render/QA separate mock; dev stress matrix | Sketch contributor/provenance or fallback decision, Lead | Draft coverage matrix; public source optional |
| R09 | Export unique correctness labels from matched dev predictions; hand-count oracle; support/ACK | Accepted matching/status policy, Lead/AI; actual dev predictions, AI2 | Existing oracle outputs; no calibration claim |
| R10 | Freeze evaluator/membership/pins; dev runner rehearsal; final-open/access decision | Frozen complete runner, AI2/AI1; host/custodian permissions, Lead | Tiny/dev preflight; no final access |
| R11 | Run pinned final, preserve all requested outcomes, score and quality disposition | Explicit final-open decision and provisioned runner/host | R01–R09 independent work |
| R12 | Assemble reproducibility/data card; verify storage; peer subset replay; reconcile Issues | Final artifacts as applicable; actual independent replay, peer | Pin source/recipes/known limits now |

## Execution evidence

### M01 — LOCAL PASS

Shared duplicate screening now rejects every present base with zero or multiple
clean representatives. Current call sites are D2.2 report generation and duplicate
review validation (including public planner); per-sample semantic loading is not
changed. Valid base subsets retaining clean+variants remain supported.

Actual commands, with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B`:

- `-m unittest discover -s tests/unit -p test_data_pilot.py -v`: 13 PASS.
- `-m unittest discover -s tests/unit -p test_data_duplicate_review.py -v`: 8 PASS.
- In-memory mutation of `require_clean_representatives` to a no-op: the new
  rebound-hash test fails for all three malformed inventories as expected. No
  source mutation persisted. CLI negatives run in normal and optimized modes.
- Original positive snapshot remains 71 pending, risk components 16+4, 20 bases /
  80 samples quarantined, zero members. No snapshot/report/review hashes changed.

Hosted CI and reviewer F2 closure require publication of the new head; NOT_RUN.

### M02 — LOCAL PASS

Records CLI regression now uses a fresh nested output for `--full-set`, asserts
`full D1.2 requires 20 IDs` and no created directory in normal/-O. A separate CLI
call asserts no-overwrite stderr and byte preservation. Product exporter unchanged.
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover -s tests/unit
-p test_data_training_records.py -v`: 6 PASS (18.140 s).
Disposable subprocess wrapper dropping `full_set` makes the test fail for both
normal and optimized CLI invocations; no production mutation persisted.

### M03 — LOCAL PASS

Worker derives its bound from `workload()` and checks any declared counter is an
integer equal to that result. Missing optional counter no longer causes KeyError;
sample count is still bounded by computed attempts. Forged counters fail before
platform probes/stage work. Resource import remains Linux-only after preflight.
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover -s tests/unit
-p test_data_benchmark.py -v`: 12 PASS (0.386 s). This is guard/failure-accounting
verification, not a new performance/model capacity measurement.

### M04 — LOCAL PASS

[Handoff index](data-handoff-index-2026-11-23.md) removes dependence on a private
evaluator ZIP by giving a pinned-source/fixture recipe, inputs and exact scores.
Actual full20 verify/export matched existing manifest/records hashes and counts;
11 handoff regressions PASS. Evaluator CLI replay from isolated exported source
matched every historical hand-counted oracle. [Receipt](data-handoff-receipt-2026-11-23.json).
Large outputs stay ignored in `artifacts/evaluation/data-mini-20261123`.
Existing transfer URL retained; remote receiver access and ACK remain unverified.

### M05 — LOCAL PASS (preparation only)

Runnable `vietdoc.data.review_batches` validates the pinned actual source through
the existing records exporter, then prepares eight batches covering all 71 pending
pairs exactly once: 33 cross-split first, 38 same-split second. Clean asset/content
hashes and lineage/catalog support are pinned; no verdict or inspection is invented.
Four focused tests PASS. Actual normal/-O commands produce identical bytes.
[Queue and next peer action](data-review-batches-2026-11-23.md).
