# Data increments — 22/11/2026

Execution ledger for the user-requested decomposition of `Data-giao-viec.md` v2.
Issue/PR acceptance remains authoritative; LOCAL PASS below never means consumer
ACK, Lead approval, merged, or hosted CI. Work starts at `develop@e040e94` on
`codex/SE-22_data_handoff_increments`. The original local execution authorized
commits only. Existing untracked documents/assets remain untouched.

Follow-up publication request on 22/11/2026 authorizes push and a review PR into
develop. The candidate branch is now `feature/SE-22_data_handoff_increments`.
The historical local/remote `codex/issue-38-duplicate-review-packet` was renamed
to `feature/issue-38-duplicate-review-packet` without changing either head (local
`055d7c6`, remote `1e1e5c1`); no history was overwritten to synchronize them.
Source/test bytes still match the verification inventory below. Hosted CI and
consumer/Lead acceptance must be read from the publication PR; the original local
results do not establish those outcomes. Merge remains a Lead decision.

## Mini tasks and commit boundaries

Each row is a reviewable behavior or evidence output. Existing accepted work is
reused; no empty commits or duplicate implementations. Source fixes and their
regressions stay together. Evidence-only rows can share their owning source
commit; external ACK/approval rows do not require artificial commits.

| ID | Parent / Issue | Output and acceptance | Dependency / initial status |
|---|---|---|---|
| A1 | D1-A | Pin current develop and six PR heads; identify own deltas and old fixes to retain | In progress; read-only GitHub inventory |
| A2 | D1-A / #36 | Integrate only #77 adapter source/tests and API contract on current develop; legacy API and status regressions pass | #77 existing source, not consumer approval |
| A3 | D1-A / #38 | Integrate #78 duplicate validator/tests and existing pending snapshot without reverting baseline | A2; own delta only |
| A4 | D1-A / #38 | Integrate #80 portable bounded benchmark and tests; preserve Linux-only measurements and guards | A3; own delta only |
| A5 | D1-A | Current candidate verification, mandatory suite inventory, proposed keep/close table and preserved-fix audit | A2–A4; Backend owns CI changes |
| B1 | D1-B / #22 | Verify existing full20 ZIP/inventory/checksums into a fresh root, counts and provenance recorded | Existing local bundle; no rerender/repack |
| B2 | D1-B / #22 | Re-run malicious bundle/path/member/hash/semantic rejection regressions; fix a demonstrated gap if found | B1 and existing tests |
| B3 | D1-B / #22 | Publishable receipt/index with version/hash, existing transfer URL and exact relative-root commands | B1; local artifact, no upload required |
| B4 | D1-B / #22, #41 | AI1 receiver verify20 and native20 ledger; AI2/Backend receipt ACK | External owners; not satisfied by Data self-run |
| C1 | D1-C / #36 | Reproduce receipt/invoice pointer/status/value vectors and invalid-input regressions | A2; actual verified snapshot |
| C2 | D1-C / #36 | Runnable Data export of verified training records with paths/hashes/gold/statuses, no invented mask policy | C1; inspect existing API before adding |
| C3 | D1-C / #52 | AI2 reader/decoded batch and approved target/mask/loss treatment for partial labels | AI2 owns actual training consumer; no consumer source yet |
| D1 | D1-D / #38 | Verify pinned 480-asset snapshot and queue against current source; preserve historical bytes | #85 accepted prep |
| D2 | D1-D / #38 | Inspect first cross-split batch images/content/lineage; versioned evidence and justified dispositions | D1/A3; uncertain pairs remain unresolved |
| D3 | D1-D / #38 | Peer review first batch, then remaining cross-/same-split batches | Peer/Lead acceptance; do not invent human sign-off |
| D4 | D1-D / #38 | Grouping proposal/rebuild with transitive confirmed relations, whole-group exclusions, before/after checks | Confirmed dispositions and Lead split decision |
| E1 | D1-E / #38 | Capacity/modality/context/rows/transcript/geometry inputs and explicit mini-pilot scope | AI1/AI2/Lead inputs; Data benchmark alone insufficient |
| E2 | D1-E / #38, #39 | QA/render/validate approved train/dev members; counts, provenance, hashes and status support | D4/E1; no historical final relabeling |
| E3 | D1-E | Package/index and Data reader replay for both consumers | E2; independent gold, no OCR as gold |
| E4 | D1-E / #44, #52, #57 | AI1 pinned OCR cache/dev baseline and AI2 actual batch/tiny pilot ACK | AI1/AI2 execution |
| F1 | D1-F / #35, #37, #43 | Run scalar/table/OCR/evidence known-score oracles with explicit numerator/denominator/exclusions | Existing #14 evaluator; no policy acceptance implied |
| F2 | D1-F | Replayable evaluator packet/index with commands, tiny predictions, expected results and version hashes | F1; independent recipient can recompute |
| F3 | D1-F | Evaluate actual AI1 OCR and AI2 prediction packets, keep failed/missing IDs | Producer packets/pins not yet received |
| F4 | D1-F / #53 | Consumer replay ACK and Lead metric/split protocol decision | AI1/AI2/Lead |
| V1 | D2-A / #38, #39 | Approved capacity/base/family targets and support gaps | G0 #55/#56/#67, pilot acceptance |
| V2 | D2-A / #39 | New independent layouts/stress slices with authors/source/QA | Peer layout inputs and approved scope |
| V3 | D2-A | Dataset v1 train/dev, isolated proposed final, integrity/group audit and actual AI2 batch | V1/V2 and accepted grouping |
| P1 | D2-B / #54 | Dev-based metric/threshold/normalizer/exclusion proposal and frozen version pins | #53 Lead acceptance before final |
| P2 | D2-B | Custodian/host permissions and noninteractive pinned runner dev dry-run | Lead host/access and AI2 runner |
| P3 | D2-B / #54, #59 | Freeze with protocol/checkpoint/evaluator/ID mismatch rejection | P1/P2; final remains blocked until then |
| R1 | D2-C / #61 | Immutable final prediction/ID outcome ledger with hardware/latency evidence | Lead final-open approval, pinned candidate/runner |
| R2 | D2-C / #61 | Per-type/slice metrics, failures/support, model-card and quality limitations | R1; no tuning on opened final |
| H1 | D2-D / #61 | Data card/license/synthetic/lineage/package index and actual peer replay subset | Accepted versioned artifacts and peer replay |
| H2 | D2-D | Issue-to-artifact/ACK acceptance ledger with exact pending owners | All increments; never close role from one merged PR |

## Execution evidence

Initial state: Python 3.12.3, Pillow 10.2.0, jsonschema 4.10.3 available; no install
required. `adaptive-engineering` and `software-architect` are unavailable in the
session catalog/local skill directories; use inspect → criteria → smallest
change → verify → diff review. No subagents, model download, paid API, deployment,
inference/training, or final-data access is implied by this ledger.

Verification results and completed mini tasks below are bound to actual
source/artifact hashes and commands. Pending external rows remain pending.

## Completed local outputs and commits

LOCAL COMPLETE means the row's Data-owned output exists and was checked locally.
It does not mark its parent Issue Done or remove consumer/peer/Lead acceptance.

| Mini tasks | Local output / source commit | Evidence |
|---|---|---|
| A1 | PR heads/deltas/keep-close proposal, 41a0ccc | [Convergence](data-convergence-2026-11-22.md), [inventory/pins](data-candidate-inventory-2026-11-22.json) |
| A2 | Validated adapter/API contract, 3874693 | 12 adapter regressions PASS; source matches #77 own delta |
| A3 | Duplicate validator/pending snapshot, a305851 | 8 regressions PASS; source matches #78 own delta |
| A4 | Portable bounded benchmark, eb24d73 | 10 guards PASS; fresh Linux 8 attempts/6 accepted/2 rejections; [32 source pins](data-capacity-increments-2026-11-22.json) |
| A5 | Preserved-fix tree review, CI inventory handoff and combined verification | Local results below; hosted CI/Lead integration decision remain external |
| B1 | Existing full20 verified into a new root | 20 IDs, 10/10 types, 204 rows, 102 members; original manifest/archive hashes retained |
| B2 | Missing-member/rebound-ID alias negatives, ee38f61 | 11 handoff tests PASS; rejected input publishes no output |
| B3 | Version/hash/access/root/verify receipt, 5524671 | [Handoff](data-handoff-2026-11-22.md); existing transfer URL HEAD returns 200 application/zip; receiver ACK pending |
| C1 | Receipt/invoice four-state vectors, 5524671 | [Accessor vectors](data-label-vectors-2026-11-22.json); D1.1 content-only scope explicit |
| C2 | Runnable verified-record exporter, bc3bb89 | 5 regressions PASS; full20 export 20 records, 1138 present/12 absent; no invented mask/loss |
| D1 | 480 historical assets/queue reverified | Manifest/report/screening/hash checks PASS; original snapshot unchanged |
| D2 | First ten cross-split pair inspection, 28570fd | [Per-pair evidence](data-duplicate-batch01-2026-11-22.md); 10 distinct AI-attributed decisions, 71 pending/33 cross-split; peer sign-off pending |
| F1 | Existing evaluator tiny oracles replayed | 49 evaluator tests PASS; actual scalar/table CLI exit 0 |
| F2 | Relocatable evaluator packet, f269df3 | [Packet/index/replay](data-evaluator-replay-2026-11-22.md); independent expected scores reproduced from extracted source/fixtures |

These are 14 local mini-task outputs. Repeated focused suites are not added to
combined unique-test totals. Existing reports copied from PRs retain their own
dated evidence; only this run's commands establish the current local results.

## Remaining mini tasks and exact external inputs

| Mini tasks | Owner/input needed | Checkpoint and next action once received |
|---|---|---|
| B4 | AI1 receiver verify + native20 outcomes; AI2/Backend full20 receipts | Correct full20 bytes and replay commands ready; need actual consumer commands/environment/hash/counts |
| C3 | AI2 #52 actual reader/decoded target/batch, model/preprocess pins and reviewed masking/filtering policy | Adapter/records/four-state vectors ready; no training reader/collator source exists in current candidate to verify |
| D3 | AI1/AI2 peer review of first batch's image/content/lineage reasoning | 10 decisions ready for challenge/acceptance; remaining 71 not auto-classified while the first-batch gate is pending |
| D4 | Accepted dispositions/confirmed relations and Lead grouping/split decision | No wrong grouping confirmed in first batch; existing transitive grouping is preserved; no invented fix or whole-group exclusion |
| E1 | AI2 modality/model, max context/rows and G0 hardware/train-step/checkpoint; AI1 transcript/geometry requirements; Lead pilot scope/budget | Bounded Data measurement available; no approved pilot size inferred from scorer timing |
| E2/E3/E4 | D4/E1 first, then Data package and AI1 pinned cache/baseline + AI2 actual batch/tiny pilot ACK | Historical smoke remains historical; do not relabel its exposed final members as an untouched final |
| F3 | Actual AI1 OCR and AI2 predictions.v1 packets with manifest/version/source/runtime pins and failures | Evaluator/oracle packet ready; do not substitute synthetic known predictions for these inputs |
| F4 | AI1/AI2 replay ACK and Lead #53 metric/split protocol acceptance | Normalization/matching/evidence/calibration remain Proposed |
| V1/V2/V3 | Lead/AI2 accepted capacity/support; peer-authored independent layouts with provenance/QA; pilot acceptance | No new dataset volume, families, holdout membership or training batch invented |
| P1/P2/P3 | Lead dev-based targets/protocol, custodian/host/access approval; AI2 pinned noninteractive runner dry-run on dev | Final protocol/freeze NOT_RUN; no final-data access or permissions fabricated |
| R1/R2 | Approved final-open gate, immutable candidate/checkpoint/preprocess/evaluator pins and runner/host | Final inference/evaluation/model-card inputs NOT_RUN; do not tune on final |
| H1/H2 | Accepted versioned final package and actual peer subset replay; remaining Issue ACKs | Current ledger/package index is partial; full Data role acceptance remains open |

The execution request authorizes local implementation and commits. It does not
authorize creating consumer sign-offs, sending messages as teammates, approving
Lead gates, or treating unanswered input requests as permission. A text input
request for existing evidence/paths was issued while independent work continued;
no new supporting artifacts/decisions have been received in this run.

## Combined verification and limitations

Python 3.12.3/Linux, Pillow 10.2.0, jsonschema 4.10.3; Poppler available. Source
and test hashes in the inventory remain the same across the combined check run.
All commands below use `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src` from repo root.
Logs/artifacts remain local ignored under
`artifacts/evaluation/data-increments-20261122/`.

| Actual command/check | Current result |
|---|---|
| `python3 -B -m scripts.ci.checks tests data --separate-pdf` | PASS, exit 0: 81 discovered, 80 selected/run, 79 executed PASS + 1 canonical opt-in skip; 0 failures/errors, 1126.452 s |
| `python3 -B -m scripts.ci.checks tests pdf` | PASS: 1 selected/executed, 0 skip |
| `python3 -B -m unittest discover -s tests/unit -p test_review_regressions.py -v` | PASS: 7/7, 183.503 s |
| `python3 -B -m unittest discover -s tests/unit -p 'test_evaluation*.py' -v` | PASS: 49/49, 12.960 s |
| Full20 verification/export, scalar/table CLI, extracted evaluator packet replay | PASS; exact commands/versions/hashes in linked receipts |
| 480 snapshot assets + queue and 10 pair evidence bindings | PASS; compare pair IDs order-independently as specified by existing validator |
| `git diff origin/develop HEAD --check`; own-source parity with #77/#78/#80 | PASS at review checkpoint; final diff check recorded after ledger update |
| Shared schema/CI/Java/Flyway/evaluator/handoff/splits tree comparison | Unchanged against base; no migrations or schema compatibility change |

Combined unique checks: **137 selected/run, 136 PASS, 1 canonical opt-in SKIP**,
0 failures/errors (Data 80 + evaluator 49 + review 7 + PDF 1). Canonical reference
byte replay was not enabled; the skip is the existing allowed opt-in case, not a
new skip. [Machine verification/log hashes](data-verification-2026-11-22.json)
record accounting. Focused reruns are excluded from this total. Final source/test
hash comparison against the inventory and whitespace/diff checks PASS; only the
user's pre-existing untracked files remain outside the committed candidate.

An initial exporter test exposed tuple/list JSON shape mismatch and was fixed in
the source before commit; final focused tests pass. An exploratory metadata check
incorrectly compared ordered base-ID arrays; the documented stable pair ID is
order-independent. The corrected binding check passes without changing data or
lowering the product validator. These are not hidden failed product cases.

Basic secret-pattern/path review found no private keys/tokens or binary/runtime
assets in the candidate diff. No dependencies/services/models/datasets were
installed/downloaded, no inference/training was run, no final was opened, no
GitHub state/settings were changed. The HEAD request fetched only HTTP headers.
Native Windows, fresh installed-wheel smoke, Java/PostgreSQL/browser/provider E2E
and hosted CI are NOT_RUN on this local candidate. Tests of existing synthetic
smoke families named final do not open a frozen holdout.
