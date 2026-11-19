# M-N1/M-N2/M-N3 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task-by-task.
> User yêu cầu plan rồi thực hiện. Không spawn agents, commit/push, sửa GitHub,
> tải model/dataset, cài dịch vụ hoặc thuê tài nguyên.

**Goal:** Bàn giao rules baseline receipt/invoice có logic và offline predictions
Data đọc được, release hardening R11/R12, cùng feasibility constraints có evidence.

**Architecture:** Giữ neutral schemas/normalizer và private service. AI2 snapshot
consumer nhận cấu trúc OcrPage/PreparedPage proposal đã đọc tại AI1 `3712c65`, không
copy owning types hoặc tự nhận shared approval. Scalar mapping theo label; table
grouping theo header/layout, fallback ordered cells chỉ khi unambiguous. Evidence
dùng matcher AI1 khi được cấp; thiếu matcher/geometry thì regions rỗng và flags.
Offline harness tách predictions khỏi gold, xuất artifact D3.1/D3.2-compatible.

**Tech Stack:** Python stdlib + existing jsonschema/pytest, Docker Linux tests.

**Spec:** `next-ai2-2026-10-30.md` user cung cấp;
[AI2 roadmap](../ai-2-extraction.md), [compute protocol](../../../specs/contracts/compute-api.md),
[business schema](../../../specs/contracts/business.schema.json).
AI1 proposal `3712c65:contracts/ocr.py,pipeline/evidence.py`; Data evaluator
`origin/feature/data-d3-1` at `e001496` và D3.2 proposal chỉ là consumer references.

## Global constraints / design decisions

- Workspace feature branch hiện có tại `3a2b701`, ban đầu sạch; không tạo worktree
  hoặc merge/cherry-pick AI1/Data branches. Plan này là execution ledger, không Issue authority.
- Chỉ Vietnamese printed single-page receipt/invoice; type do caller chọn.
- Decimal strings, max 30 items, không infer money bằng arithmetic hoặc số lớn nhất.
- Không dùng sample_id/filename/gold/pointers trong extraction decisions.
- Input profile: tối đa 4096 OCR blocks, 128 Ki characters, canonical <=20MP.
- Không silent truncate; unsupported/oversize layout là typed failure hoặc explicit issue.
- Missing OCR text không là absent. Chỉ explicit absence wording mới được đánh absent.
- Confidence/confidence_method null; OCR score không thành field correctness.
- No matcher => no highlights. Prepared mapping unavailable => không nhận canonical quads.
- Fixture renderer mode là explicit opt-in; chỉ text/bbox đầu vào, bỏ annotation pointers,
  không đọc gold/labels để extract. Tất cả outputs ghi simulated OCR, không quality/native claim.
- Prediction envelope theo `vietdoc.predictions.v1`, pinned exact manifest hash,
  dataset/normalizer/OCR/preprocess/schema/model/evaluator metadata, typed failures.
- Không thay runtime compute schemas hoặc cho Python business export/DB access.
- R17 hosted run và external peer acceptance vẫn pending; không sửa lại CI writer files.

## Approaches

Chọn label/header rules từ OCR để có B0 ngay. Model-first cần artifact/approval chưa
có; hard-code theo D1 IDs hoặc đọc gold không tạo extractor hợp lệ. Geometry giúp
không zip lệch rows; ordered fallback chỉ nhận grammar đủ cột, còn mơ hồ thì abstain.
Tách snapshot consumer, scalar/table extraction và offline producer để mỗi phần
có tests riêng. Không viết evaluator thứ hai; smoke output bằng Data source cô lập.

## Review focus

- Wrapped/repeated descriptions và missing cells không dịch cột hoặc đổi row identity.
- Repeated amounts: value chọn theo label/context, không chọn highlight tùy ý.
- Absent/unreadable/unknown cùng null nhưng diagnostics khác nhau; negative quantities không fill 0.
- Hash/path/duplicate IDs/type/version và artifact provenance phải fail explicit.
- Release malformed numeric/deep JSON không chặn good release; Windows drive/link containment reject.

## Task 1 — M-N1 release hardening và evidence handoff

Files: `src/vietdoc/ml/release_manifest.py`, `tests/unit/ml/test_release_manifest.py`.
Interfaces: giữ `load_release`/`discover_releases`; decoder-limit errors => ReleaseError,
Windows colon/drive/reparse/resolved escape rejected trước read/hash.

- [x] Viết RED numeric/deep malformed release + good discovery; drive/colon cases.
- [x] Catch expected decoder-limit errors; resolved containment và link/reparse checks.
- [x] GREEN release/API regressions. Không claim native Windows junction nếu chưa chạy.
- [x] Ghi R17/PR-body evidence mới vào handoff local; không sửa GitHub.

## Task 2 — M-N2 OCR consumer và extraction baseline

Create: `pipeline/extraction/ocr_input.py`, `baseline.py`, `table.py`;
tests `tests/unit/pipeline/test_baseline.py`.

Interfaces: `snapshot_page(page, prepared=None) -> Page` internal immutable snapshot;
`extract_baseline(page, document_type, *, prepared=None, evidence_matcher=None) -> BaselineResult`.
Result có payload/raw_candidates/field_metadata/issues/field_states, không runtime IDs.
Typed `BaselineError(code)` cho input/profile/layout failure. Matcher hook nhận
field path/raw/context_block_ids, callers dùng AI1 EvidenceRequest/match_evidence.

- [x] Viết RED scalars/total vs line_total, receipt/invoice, absence/unreadable,
  conflicting labels, raw/normalization negatives/date/time, structural input errors.
- [x] Snapshot consumer validate types/IDs/finite canonical geometry/version/bounds.
- [x] Implement label extraction, context candidates và required FieldMetadata keys.
- [x] Viết RED table wrap/repeated desc/reordered columns/missing unit or cell,
  0/1/30/31 rows và missing geometry fallback.
- [x] Implement table grouping; no zip-shift, no silent truncation; GREEN focused suite.

## Task 3 — M-N2 offline prediction producer / CLI

Create: `pipeline/extraction/predictions.py`, `entrypoints/cli/baseline.py`,
`tests/unit/pipeline/test_baseline_export.py`, extraction README.

Interfaces: `export_predictions(root, manifest_path, output_dir, *, ocr_inputs=None,
renderer_fixtures=False) -> dict`; CLI `python -m vietdoc.entrypoints.cli.baseline`.
Real OCR input manifest maps sample_id to hash-pinned OcrPage/PreparedPage JSON.
Explicit renderer mode uses D1 regions text/bbox only and marks fixture provenance.
Output new directory/predictions.json, refuse overwrite; failures remain records.

- [x] RED tests two D1 IDs extraction without gold read, exact manifest hash/versions,
  typed failure retention, unknown/duplicate IDs, path/hash/tamper/overwrite rejection.
- [x] Implement producer và CLI; keep Data env separate, no Data renderer/Pillow imports.
- [x] Smoke CLI on tiny fixtures; test output schema/business payload, all metadata keys.
- [x] Run actual Data evaluator in ignored isolated source overlay; report preliminary
  scalar/table observations only where evaluator actually measures them.

## Task 4 — M-N3 constraints và consumer documentation

Create docs `2026-11-01-baseline-handoff.md` và `2026-11-01-model-constraints.md`;
update AI2 README/HISTORY only, không duplicate roadmap.

- [x] Đo CPU/RAM/GPU/VRAM/disk/packages và local model-artifact inventory không load model.
- [x] Ghi candidate/artifact/license/revision/profile chưa được cấp/duyệt, BLOCKED G0
  có điều kiện unblock. Không nộp fake training entrypoint hoặc planned execution là PASS.
- [x] Ghi inference/training dependency compatibility (AI1 Pillow12 vs train Pillow13),
  same entrypoint future notebook plan và checkpoint/resume acceptance.
- [x] Handoff M-N1 inventory/CI pending, M-N2 commands/results/limitations, M-N4 actual OCR
  và M-N5 training gates. Prepared/geometry/matcher consumer review vẫn pending AI1.

## Verification / ledger

- [x] Focused unit/contract/API/architecture và strict AI runner (new pipeline tests auto-discovered).
- [x] Docker test target trên source cuối, zero unexpected skips.
- [x] AI1/Data consumer smoke tại pinned source; không merge product branches (self-run, không independent reviewer).
- [x] Inspect diff/links/secrets/schema compatibility; self-review riêng, không peer approval.

Pre-flight: Tasks 2/3 share BaselineResult và input snapshots; no business IDs/gold
inside extractor. Task 1 không đổi normalizer/contracts. Task 4 chỉ report measurements.
Ruling: user yêu cầu plan rồi thực hiện; workflow inline trong workspace hiện có,
không thêm approval/agent/commit/worktree steps từ skills trái AGENTS/user scope.

Baseline Windows: `scripts.ci.ai --allow-windows-symlink-skip` → 349 passed,
1 symlink skipped, 58 subtests passed; 350 collected. R17 connector query cho
`3a2b701` chưa trả PR workflow runs, không tự suy diễn nguyên nhân/hosted success.

## Execution ledger / final evidence

Task 1 complete (local code): RED 3 release failures → GREEN release/API 89 passed,
1 Windows symlink skipped. Native Windows drive-relative controlled file ngoài release
nhưng trong temp root bị reject. Reparse guards có code; native junction/cross-drive
fixture matrix chưa chạy. Không tự nhận model release approval.

Tasks 2/3 complete (fixture baseline/export): RED missing functionality, sau đó
regressions RED→GREEN cho scalar-looking descriptions, segmented footer, row reading
order, unsupported transforms, malformed artifacts/matcher và multiple tables.
Focused baseline/export cuối: **51 passed**. CLI reviewed artifact 2 ok/0 failed.

Ruling: B0 profile chỉ hỗ trợ axis-preserving prepared layout; reject rotate/shear/
projective thay vì tự implement AI1 geometry hoặc giả identity. Chi phí: các trang
ngoài profile chờ processed-frame adapter. Đã ghi limitations trong source README.
Ruling: producer pin `target_evaluator_versions`, actual evaluator version/source hash
nằm ở Data report sau execution; không ghi một evaluator_version giả đã chạy.

AI1 consumer `3712c65` types/geometry/matcher smoke pass, exact 3 blob identities khớp;
Data D3.2 consumer `a0d71b2112437e0b25b6b20cbc8fdcc8b6da4c37` parse/scoring pass.
Self-run tại `.verification/mn2`, không merge/copy owning source vào product. D1 tiny
fixture observations: scalar 12/12 present, false-fill 0, table 30/30 cells và 6/6 rows;
default CLI evidence 0/42. Không native/holdout/model quality claim. B0/M0/M1 fair=false.

Final Windows AI runner: **412 passed, 1 skipped, 58 subtests passed**, 413 collected,
no policy failures; pip check pass. Final Docker Linux Python3.12: **413 passed,
0 skipped, 58 subtests passed**, build exit0/pip check pass. Image manifest list:
`sha256:168508347b9ff6ab19324aa33af84fe75ad501639e852f38e9c56ee1382eb134`.
JUnit: `test-results/mn2-ai-windows.xml`, `test-results/mn2-ai-linux.xml` (ignored).
Không rerun full Data/render/package matrix trong AI env thiếu PIL; không claim all-repo pass.

Task 4 complete as constraints deliverable: host hardware và cached GPU train image
probe measured; CUDA available nhưng không có verified local model release/candidate
approval. Candidate metadata/revision/license proposal đã chuẩn bị; G0 **BLOCKED**.
Inference/train-step/checkpoint/reload và actual OCR composition **NOT_RUN**.

Final self-review: fixed multiple-table silent omission bằng RED→GREEN, green suite;
input/output hashing/path/identity/metadata, source reading order và neutral schema
compatibility reviewed. No new schema/normalizer/CI-writer/data changes. Không secrets,
model/dataset binaries hoặc runtime artifacts trong diff. Không peer/Lead approval,
GitHub writes hoặc commit/push. R17 và external acceptance vẫn pending.
