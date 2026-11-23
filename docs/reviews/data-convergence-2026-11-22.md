# Data candidate convergence — 22/11/2026

Mini tasks A1–A5; refs #22/#36/#38. Local candidate starts at
`develop@e040e94bb20509055d06fa0182e05a565e588b94`, after #87. Source/test/remote
pins and discovered inventory are in
[machine snapshot](data-candidate-inventory-2026-11-22.json). No push/PR/close/
merge/CI dispatch or branch deletion took place. Existing untracked files remain.

## PR disposition proposal

| PR / head | Base / own change | Candidate treatment and pending outcome |
|---|---|---|
| #10 / be2c38f | develop; historical D2.1 generator/validator | D2.1 source/config/snapshots already in accepted #14 baseline. Compared old d21.py/validation.py with current develop: current adds UTF-8 and transcript scope/order gates; no old-only product fix identified. Propose Lead closes as superseded after coverage review; do not merge old tree over fixes. |
| #12 / 3026231 | develop; historical D2.2 families/augmentation/group split | Baseline already has this source plus strengthened consumer/quality/occurrence/catalog checks and handoff. Propose Lead closes as superseded after review; 81 screening dispositions/pilot acceptance are separate open work. |
| #13 / e001496 | develop; historical scalar/OCR evaluator | Baseline contains scalar/OCR plus semantic gold validation, exclusions, D3.2 and diagnostics. Propose Lead closes as superseded after review; actual packets/protocol acceptance remain open. |
| #77 / dd85080 | develop; 7-file adapter delta relative to its synced base | Reused source 3c135f6 and contract f08de75 in local 3874693; no inherited schema/CI changes. Added records exporter separately in bc3bb89. Original PR stays Draft/pending consumer review; Lead decides whether this candidate supersedes it. |
| #78 / fc2877e | develop, inherited #77; own duplicate validator/tests + pending metadata | Reused only 72456d9/fc2877e delta in a305851 on the new baseline, avoiding its stale inherited tree and conflicts. First inspection batch is separate 28570fd. Original PR remains unchanged/pending Lead integration decision. |
| #80 / b36ad65 | feature/duplicate_review_audit; own bounded benchmark + portability fixes | Reused own four commits d5eaa53/48fa297/b75df3c/b36ad65 in eb24d73. No merge into parent feature. Fresh bounded Linux run completed with exact current source pins; original PR remains Draft, required integrated CI pending. |

This is functional/source coverage review, not a claim that old commits are
patch-equivalent after squash merges. Multiple merge bases make GitHub's old
three-dot file lists misleading: files shown added there can already exist on
develop. The candidate uses specific own deltas and reviews the resulting tree.
Historical reports retain their dated observations; new reports supersede their
current-state conclusions without rewriting those files.

## Preserved boundaries/fixes

Tree diff against develop leaves shared schemas, CI scripts/workflows, Java,
Flyway, evaluator source, handoff verifier, splits, generator values/renderers and
family catalog unchanged. The only modified baseline runtime file is
`generator/integration.py`: expose the already checked labels, retain `check_sample`
and `load_artifacts` wrappers, and adapt full-set tuple unpacking. Review confirms
quality derivation, source lineage, vocabulary lookup, exact occurrences and
sidecar/schema/hash/path gates remain. New adapters/duplicate tooling/benchmark
are additive. Legacy Python business scaffold is untouched.

Focused suites: adapter 12 PASS, duplicate 8 PASS, benchmark guards 10 PASS;
full20 verifier and exporter commands pass. New records suite 5 PASS and handoff
suite 11 PASS. Existing evaluator suite 49 PASS. Current full Data/PDF/review
outcomes are recorded in the execution ledger once the combined run completes;
do not count repeated focused runs as distinct tests.

## Fresh bounded capacity observation

[Exact summary](data-capacity-increments-2026-11-22.json), existing Linux Data env:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.data.benchmark \
  --output outputs/capacity-data-increments-20261122 --rows 1 --repeats 1 --stage-timeout 300
```

Exit 0; four stages ok; 8 attempts = 6 accepted + 2 clipping rejections. Wall
seconds render 3.106 / strict replay 3.177 / semantic load 0.333 / scorer 0.029.
32 source pins, exact config/schema/font/manifest pins and hardware/runtime are
recorded. One observation, OS caches uncontrolled; it ran before full test jobs.
This is not a speed comparison, SLA, D2.2 augmentation/dedupe capacity, model/GPU
training budget or approval to scale the dataset. No final input was accepted.

## Exact Backend CI inventory handoff

Current Data discovery selects `test_data*.py`: 81 discovered, 80 selected when
one PDF case is delegated. Mandatory-file inventory in `scripts/ci/checks.py`
still names only values/integration/d21/d22. It does not require all modules below
to exist, and evaluator/review modules are outside that pattern.

| Module to protect | Negative behavior that must survive collection |
|---|---|
| test_data_label_adapter.py (12) | invalid/missing pointers/status/hash/path; no partial yield; null statuses differ |
| test_data_training_records.py (5, new) | bad later sample cannot publish records; manifest drift; output overwrite; D2 path base |
| test_data_duplicate_review.py (8) | missing/duplicate/unknown dispositions, drift and incomplete evidence cannot clear review |
| test_data_benchmark.py (10) | unsupported platform/import guards, bounded workload, worker failure/timeout accounting |
| test_data_handoff.py (11) | missing/duplicate/mutated members, traversal/ID aliases, no-overwrite and relocated bytes |
| test_data_d2_semantics.py (5) | forged clean quality, repeated occurrences, catalog vocabulary mismatch |
| test_evaluation*.py (49 across 4 modules) | semantic gold bypass/drift, partial/failure accounting, hand-counted scalar/table/evidence oracles |
| test_review_regressions.py (7) | actual producers/partial labels, strict mutation rejection normal/-O, encoding/geometry boundaries |

Backend owns required inventory/workflow changes. This local handoff records exact
modules/cases without changing ownership or claiming a hosted gate for unpushed
commits. Native Windows, wheel fresh-install and actual-provider E2E are NOT_RUN
on this candidate. Existing PR/develop greens are historical evidence only.
