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

Pending. Each owning increment appends actual results; no command in this file is
claimed executed merely because it appears in a plan.
