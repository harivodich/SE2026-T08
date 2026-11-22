# Data increments — 22/11/2026

Execution ledger for the user-requested decomposition of `Data-giao-viec.md` v2.
Issue/PR acceptance remains authoritative; LOCAL PASS below never means consumer
ACK, Lead approval, merged, or hosted CI. Work starts at `develop@e040e94` on
`codex/SE-22_data_handoff_increments`. No push, PR, merge, or external messaging
is authorized in this run. Existing untracked documents/assets remain untouched.

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

Verification results and completed mini tasks will be appended against actual
source/artifact hashes and commands. Pending external rows remain pending.
