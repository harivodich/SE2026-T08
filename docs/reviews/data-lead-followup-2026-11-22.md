# Data — Lead supplement follow-up, 22/11/2026

Follow-up to [the increment ledger](data-increments-2026-11-22.md), on PR #88.
The user asked to inspect the two supplied files and execute the newly actionable
mini tasks, with separate logical commits, checks and publication for review.
The supplied files remain untracked; their instructions do not themselves grant
model downloads, host access, peer sign-offs, approval or protected-branch merge.

## Evidence and decisions received

Inputs are `Lead-quyet-dinh-va-evidence-cho-Data.md` and
`Evidence-native-19-11-pham-vi.md` in the user-provided supplement folder.
Exact input byte hashes are recorded in the accompanying follow-up receipt.

- L01 fixes current modality: AI1 OCR/preprocess/geometry, AI2 extractor from
  text/layout to business JSON. Data no longer waits for modality clarification
  to prepare model-neutral records/grouping/evaluator. Model/context/rows and
  actual infer/train-update/save/reload capacity still require AI2 evidence.
- L02 allows pilot preparation before G0, without inventing minimum support.
  Known source/family/base/duplicate relations form stable transitive groups.
  Unresolved connected components must be quarantined in full; no silent
  truncation, member-level dropping, random resplit or historical-final relabeling.
- L03 releases evaluator oracles before actual producer packets; those outputs
  already exist in #88. Actual packets/ACK and dev-based numeric targets remain
  separate. No threshold was accepted by the supplied decision.
- L04 does not provision a final host. `nvit-train` is a candidate; capacity,
  noninteractive runner/dev rehearsal and real custodian isolation remain open.
  This is not a prerequisite for model-neutral Data preparation.
- L05 retains actual consumer ACK, partial-default and Lead merge gates. The
  supplement does not accept the first duplicate inspection batch or close #41.

The native summary reports four historical synthetic HTTP inputs (receipt PNG,
invoice PNG, receipt JPEG and invoice PDF) with 200 responses and two matching
totals, plus busy/hash rejection probes. It pins an older candidate and runtime;
the raw native report/model hashes/logs are not in the supplied folder. Treat this
as supplied historical smoke evidence, not a new execution, native20, CER/WER,
extractor G0, checkpoint/pilot quality or Java E2E. PR83 source/approval cannot
substitute for those missing execution artifacts.

## Mini tasks for this follow-up

| ID | Output / acceptance | State |
|---|---|---|
| N1 | Pin supplied inputs; map L01–L05/native scope against current source/GitHub; update stale dependency statements | Local complete; initial scope commit d224ddf |
| N2 | Runnable pilot planner: stable confirmed groups, separately labeled unresolved components, whole-component exclusions, reasons and before/after type/split/base/variant counts | Source/regressions complete at e71f763; 11 PASS |
| N3 | Run planner on exact historical manifest/report + current batch review; verify bindings/no mutation; report remaining members/support | Local complete; actual plan and 480 asset hashes replayed |
| N4 | Prepare/verify train/dev package if both types have eligible members in both splits; otherwise record exact quarantine IDs/owners needed to unblock | Blocked by membership: all 20 bases quarantined, no eligible train/dev; not G0/host |
| N5 | Focused compatibility checks, updated ledger/PR evidence and push to existing review candidate | 73 focused PASS; publication/hosted CI tracked in PR #88 |

Group planning is metadata/review preparation. Asset/gold/pixel QA, peer acceptance
and actual AI2 reader still gate the accepted pilot; a nonempty proposed plan alone
will not declare training/quality readiness. Existing historical manifests and
dispositions must remain byte-identical.

## Actual execution and support gap

[Input/output pins and focused verification](data-lead-followup-inputs-2026-11-22.json)
and [the complete group/component/exclusion plan](../../datasets/manifests/d22-pilot-plan-20261122.json)
are safe tracked outputs. All historical manifest/report/disposition bytes are
unchanged. Existing local PNG/PDF/gold/transcript/labels/regions inventory was
rechecked: 480/480 asset hashes match; no rerender or new pixel/gold QA claimed.

Actual command from repo root (stdlib-only planning, no model/runtime service):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.data.pilot \
  --manifest datasets/manifests/d22-smoke-v01.json \
  --report datasets/manifests/d22-report-v01.json \
  --review datasets/manifests/d22-duplicate-review-20261122-batch01.json \
  --output datasets/manifests/d22-pilot-plan-20261122.json
```

Exit 0 means the diagnostic plan was computed, **not** that a pilot was accepted.
Output status is `blocked_membership`; both types have zero eligible train/dev
bases. Recomputing the plan equals the tracked JSON. All input hashes remain
unchanged. CLI refuses overwrite; invalid/incomplete/drifting review or a frozen
snapshot is rejected, including under optimized Python.

| Snapshot accounting | Before | After quarantine |
|---|---:|---:|
| Unique base documents | 20 | 0 |
| Samples including variants | 80 | 0 |
| Receipt train/dev/final bases | 6 / 2 / 2 | 0 / 0 / 0 |
| Invoice train/dev/final bases | 6 / 2 / 2 | 0 / 0 / 0 |

The 71 pending screening edges form risk components of **16 and 4 bases** after
propagating through source/family/assignment/base relations. Every component has
unresolved edges, so all 80 samples are listed with exclusion reasons. The plan
keeps positive lineage/exact-content/image/duplicate relations separate from risk
connectivity: pending dHash candidates are not mislabeled confirmed duplicates.
Shared scalar totals never create a union. Historical final members are never
converted to train/dev, and no group is silently moved to hide a conflict.

The 10 distinct decisions remain Codex-attributed proposals pending peer review;
the supplement does not grant human sign-off. If those decisions change, issue a
new review snapshot and recompute the plan; do not modify its old hash or bypass
the missing-edge guard. Existing group labels/dispositions do not authenticate a
reviewer or replace Lead acceptance.

**Unblock N4:** AI1/AI2 peer checks first-batch reasoning; Data continues the
remaining pending image/content/lineage review under the agreed batch process.
Recompute full components after accepted dispositions and obtain Lead membership
acceptance. Prepare the verified model-neutral archive once both type/split pairs
have eligible support, report any limited coverage, then get AI1 cache and AI2
reader ACK. Do not emit an empty training archive or wait for a final host/G0 as
the reason to stop this review work.

## Verification and publication scope

Python 3.12.3/Linux, existing Data dependencies only. Actual focused commands,
with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src` and `python3 -B -m unittest discover
-s tests/unit -p PATTERN -v`:

| Pattern | Result |
|---|---|
| test_data_pilot.py | 11 PASS, 1.965 s (normal/-O CLI covered inside suite) |
| test_data_duplicate_review.py | 8 PASS, 0.448 s |
| test_data_training_records.py | 5 PASS, 15.054 s |
| test_evaluation*.py | 49 PASS, 10.234 s |

73 unique focused tests PASS, no skips/failures. These are the follow-up results;
do not add them to the original full-run count as though repeated tests were new.
The planner is an additive offline module; baseline generator/validator/splits,
evaluator/API, schemas, CI, Java and model/partial-default behavior are unchanged.
Full Data/PDF/review/Windows/installed-wheel/provider E2E are NOT_RUN locally on
this follow-up source. Hosted PR CI belongs to its actual head, not the old head.

New test inventory handoff to Backend: `test_data_pilot.py` (11), protect the
missing-disposition, frozen/drifting input, transitive whole-component/variant
quarantine, immutable split, exact-vs-screening and no-overwrite negatives.
Current `test_data*.py` discovers it; mandatory-file ownership remains Backend.
