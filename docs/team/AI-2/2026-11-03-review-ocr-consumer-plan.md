# PR3 review fixes và Issue #23 — Implementation Plan

> Thực hiện inline, từng task bằng `superpowers:executing-plans`; không spawn agents.
> Yêu cầu ngày 03/11/2026: lập plan cho mục 1 và 2 của bản tổng hợp handoff;
> mỗi mục nhỏ sửa xong, kiểm tra xong phải commit riêng trước khi sang mục kế tiếp.
> Tài liệu này là kế hoạch, chưa là execution evidence hoặc approval của Lead.

**Goal:** Sửa A1–A4 của PR3 và chứng minh consumer AI2 nhận được semantics OCR v2,
evidence và hai output native D1 trong Issue #23 bằng code chạy lại được.

**Architecture:** Giữ B0 conservative, private compute và neutral schemas hiện có.
Consumer nhận snapshot provider SHA pin, không merge nguyên branch AI1. Tách parse,
diagnostic propagation, evidence acceptance và B0 observed-output report. Không nối
HTTP provider/runtime pipeline trong increment này.

**Tech Stack:** Python, pytest, jsonschema Draft 2020-12, GitHub Actions;
Java/Web chỉ kiểm ảnh hưởng khi tích hợp develop, không nhận thêm backlog Backend.

**Spec:** [Issue #23](https://github.com/harivodich/SE2026-T08/issues/23),
[compute protocol](../../../specs/contracts/compute-api.md),
[extraction ownership](../../../src/vietdoc/pipeline/extraction/SPEC.md),
[AI2 notes ownership](SPEC.md),
[provider proposal tại SHA pin](https://github.com/harivodich/SE2026-T08/blob/7d96e93bf8315beb6fa33807231316e957671249/docs/ocr-input-proposal.md).
Review nguồn: `team-handoff-2026-11-03/02-gui-rieng/ai2/review-day-du.md`
và `cong-viec.md` trong gói Downloads người dùng cung cấp.

## Snapshot khảo sát

- Root `E:/OCR_SE`; branch PR3 `feature/AI2-M2_ai_service_docker`.
- Consumer HEAD `1bc7fe84b5290d9f29b6bda8d8209832b490ad12`, trùng review handoff.
- Provider PR4 pin `7d96e93bf8315beb6fa33807231316e957671249` theo Issue #23.
- Local `origin/develop` mới ở `4ed73028782b0dea2a477b5047cd60666266f9c6`,
  `origin/feature/AI1_preprocess_ocr` ở `26bd4e1`: refs local chưa cập nhật.
  PR4 metadata ghi base `729be6fe493dc00e1d7cb87e7db94b94c79a0816`.
  Phải lấy base hiện hành trước integration; không dùng API base cũ của PR3.
- Workspace có 10 tracked docs đang sửa trước task, gồm ADR/model notes/AI2 plans,
  HISTORY/README và `src/vietdoc/ml/configs/README.md`. Không stage/commit chúng.
- Đã đọc Issue #23, PR3/PR4 metadata, golden v2, OCR types/evidence signatures
  và native bundle tại provider SHA pin bằng connector read-only.
- Native `d12-receipt-03` và `d12-invoice-04` thực sự có `artifact_version=2`,
  `recognition_status=complete`, `unreadable_count=0`. Chúng không là native partial evidence.
- `snapshot_page()` hiện không đọc version/unreadable/status/flags; parse được blocks
  chưa chứng minh metadata v2 được validate hoặc giữ qua consumer.
- Chưa chạy tests trong lượt lập plan. Kết quả 412 passed/1 skipped trong handoff là lịch sử.

## Global Constraints

- Ngoài phạm vi: hardware report, GPU/model spike, tải weights/dataset, train/fine-tune,
  runtime OCR→service composition, HTTP provider, Java/browser E2E và deploy.
- Không sửa authoritative shared schemas, Java DTO, approval policy hoặc ADR status.
- Money/quantity là decimal strings; field confidence và confidence_method giữ null.
- Missing/unknown khác explicit absent; unreadable detection không được biến thành text giả.
- Giữ raw OCR, detection IDs, canonical quads, geometry reasons và provenance.
- Không dùng transcript/gold/labels làm inference input; không sửa OCR theo sample gold.
- Không đổi default v2 của provider hoặc tự đóng R04 AI1; R04 AI1 là partial policy,
  khác R04 AI2 về deadline accounting đã có regression.
- Commit local được người dùng cho phép theo từng mục; chưa được push, tạo/sửa PR,
  comment Issue, thay settings, merge PR vào develop/main hoặc deploy.
- Không reset/clean/force-push, không ours/theirs toàn file, không tự stash docs của người dùng.
- Mỗi commit chứa fix + tests + runbook liên quan; không commit RED hoặc commit rỗng.

## Approaches và thứ tự

Chọn sửa nhỏ theo finding trên nền develop đã kiểm, rồi nhận provider fixtures SHA pin.
Import cả branch AI1 sẽ trộn ownership và conflict; đợi full pilot/model không cần thiết
vì consumer acceptance có thể chạy từ observed JSON và dependency-free provider types.

Thứ tự commit: **1.1 → 1.2 → 1.3 → 1.4 → 2.1 → 2.2 → 2.3 → 2.4**.
Nếu một mục đã được base mới sửa, kiểm chứng và ghi inherited SHA; không tạo commit giả.

## Review Focus

1. Installed package ngoài checkout, không PYTHONPATH: schema lookup phải rõ và fail khi thiếu config (1.2).
2. Footer số đứng trước nhãn và numeric continuation hợp lệ: không nhầm tiền khách/phantom row hoặc xóa hàng thật (1.3).
3. Release NUL cạnh release tốt, và toàn release lỗi: isolate lỗi, readiness không false success (1.4).
4. Partial/all-unreadable/no-detection và version metadata mâu thuẫn: giữ diagnostic, không suy absent (2.1–2.2).
5. Số lặp/merged label-value/missing geometry: source abstain đúng, confidence null, báo coverage giảm (2.3–2.4).

## Trước implementation — bảo toàn workspace và chuẩn bị evidence

- [ ] Kiểm lại root/branch/status/remote, diff có sẵn và Git identity hiệu lực; không tự đổi identity.
- [ ] Chuẩn bị worktree tích hợp riêng từ consumer HEAD bằng workflow worktree của repo.
      Giữ branch PR3 hiện có; dùng branch local tạm cho candidate để docs đang sửa ở root
      không lọt merge/commit. Ghi mapping candidate branch/PR3; không tự push branch tạm.
      Sau này chỉ đưa commit về branch PR3 khi kiểm chắc dirty docs được giữ nguyên.
- [ ] Đọc AGENTS/SPEC ở base mới; fetch develop/provider refs được phép để lấy snapshot,
      pin SHA và merge-preview trước khi sửa. Không đổi target sang main.
- [ ] Kiểm môi trường Python/dependencies đã có. Tách serve/test, Data và provider snapshot;
      không cài chồng env Data, không tải models. Thiếu dependency/network ghi rõ.
- [ ] Giữ logs/JUnit/repro trong `test-results/` hoặc `.verification/` ignored;
      chỉ đưa fixtures hư cấu nhỏ và báo cáo an toàn cần review vào Git.

## 1.1 — A1: tích hợp develop và giữ Web/AI inputs

**Files:** merge hunks thực tế; trọng tâm `.dockerignore`, `pyproject.toml`,
`.github/workflows/ci.yml`, `scripts/ci/gate.py`, `tests/unit/test_ci_gate.py`,
`infra/ai-service.Dockerfile`, docs CI liên quan. Danh sách chính xác từ merge preview.

**Interface:** candidate giữ đồng thời dependency extras, Docker inputs và executable
CI jobs của Web/Data/AI; không thêm required context khi job chưa tồn tại.

- [ ] Ghi consumer/base SHA mới và conflict list; so từng hunk với source/SPEC Backend.
- [ ] Resolve trên candidate riêng; giữ Web assets dưới backend, schema và AI test context.
- [ ] Chạy CI gate regressions; đọc runbook/backend build entrypoint ở base mới rồi chạy
      focused checks thật tương ứng. Không bịa Java/Web commands từ snapshot cũ.
- [ ] Kiểm diff merge và Docker context; nếu Docker có sẵn, chạy AI test target và Web
      build theo runbook mới. Thiếu Docker ghi NOT_RUN, không claim hosted success.
- [ ] Commit integration riêng: `merge: integrate develop into AI2 review candidate`.
      Không gộp A2/A3/A4 vào commit xử lý conflict.

## 1.2 — A2/R17: installed schema wiring và fail-closed AI inventory

**Files:** `.github/workflows/ci.yml`, `scripts/ci/ai.py`,
`tests/unit/test_ci_ai.py`, `tests/contract/test_compute_contract.py`, `docs/cicd.md`;
`src/vietdoc/contracts/compute.py` chỉ khi regression cho thấy cần đổi loader.

**Interface:** giữ `ComputeContracts(directory: Path | None = None)` và
`VIETDOC_CONTRACTS_DIR`; job AI trỏ tuyệt đối về shared schemas trong checkout.

- [ ] Viết regression installed-layout subprocess: unset PYTHONPATH, chạy ngoài source,
      xác nhận import từ site-packages; thiếu contracts directory fail rõ, cấu hình đúng
      validate compute fixtures thành công. Chạy noneditable install thực, không chỉ copy module.
- [ ] Thêm test mandatory inventory không bỏ lọt `test_baseline.py`,
      `test_baseline_export.py` hoặc module consumer mới; xóa/rỗng module phải nonzero.
- [ ] Chạy RED rồi cấu hình env AI job/local runbook; không package lại schema authority.
      Pin minimum inventory theo collection thực của candidate, không lấy count làm quality metric.
- [ ] Chạy contract/CI runner tests và fresh installed smoke; `pip check` phải đạt.
      Giữ assertion failure, missing/empty tests, deselect, unexpected skip/xfail probes.
- [ ] Commit: `fix(ci): wire installed AI schemas and require baseline suites`.

## 1.3 — A3: scalar pairing và table footer boundary

**Files:** `src/vietdoc/pipeline/extraction/baseline.py`, `table.py`,
`tests/unit/pipeline/test_baseline.py`; `ocr_input.py` chỉ khi cần geometry accessor nhỏ.

**Interface:** giữ `extract_baseline(page, document_type, *, prepared=None,
evidence_matcher=None) -> BaselineResult` và `table_rows(Page, is_scalar)`.

- [ ] Tái hiện RED đúng footer: item Cà phê 2×20000=40000; 80000 trước nhãn Tổng tiền
      cùng visual row, 100000 tiền khách ở row sau. Assert total 80000 hoặc null+issue,
      đúng một item; tuyệt đối không chọn 100000 hoặc thêm item 80000.
- [ ] Thêm label-before/value-before, font-height lệch, cash/change, repeated amounts,
      scalar-only, thiếu quads, description giống label, wrapped/sparse/numeric continuation.
- [ ] Ghép nhãn/value bằng visual context và ambiguity handling; footer scope bao cả
      amount đứng trước nhãn. Không hard-code sample, không bỏ mọi numeric-only row,
      không dùng một height threshold làm bằng chứng duy nhất.
- [ ] Chạy baseline + exporter regressions; raw/context IDs giữ nguyên, confidence null.
      Bump B0 implementation version nếu behavior thay đổi; normalizer/schema giữ nguyên.
- [ ] Commit: `fix(ai): pair scalar values and exclude footer amounts from tables`.

## 1.4 — A4: cô lập release NUL path

**Files:** `src/vietdoc/ml/release_manifest.py`,
`tests/unit/ml/test_release_manifest.py`, `tests/integration/api/test_compute_api.py`.

**Interface:** `_contained_file(root: Path, raw_path: str) -> Path` reject invalid
path trước filesystem API bằng `ReleaseError`; `discover_releases()` giữ `(releases, errors)`.

- [ ] RED: good+bad manifest `w\u0000.bin` vẫn discover good và trả error riêng bad;
      `load_release(bad)` phải là ReleaseError, không ValueError thoát ra.
- [ ] Sửa boundary tối thiểu; không catch-all startup thành success hoặc đổi path hợp lệ.
- [ ] Chạy release tests, traversal/drive-relative/symlink regressions và readiness case
      toàn release invalid phải not-ready. Skip Windows chỉ theo policy hiện có.
- [ ] Commit: `fix(ai): isolate malformed release paths during discovery`.

## 2.1 — Issue #23: validate version và nhận golden OCR v2

**Files:** `src/vietdoc/pipeline/extraction/ocr_input.py`,
new `tests/unit/pipeline/test_ocr_input.py`,
new `tests/fixtures/ocr-artifact-v2.json`, new `tests/fixtures/ocr-ai2-source.json`;
`scripts/ci/ai.py` thêm module consumer mới vào required inventory.

**Interface:** giữ `snapshot_page(page: Any, prepared: Any = None) -> Page` và
structural object/dict input; mở rộng internal `Page` với artifact version,
unreadable regions, recognition status và review flags. Không fork owning OCR types.

- [ ] Lấy đúng golden fixture từ provider SHA pin, ghi source path/blob SHA/content hash
      trong source manifest; chỉ copy fixture an toàn, không copy implementation provider.
- [ ] RED: legacy v1 shape còn dùng được; explicit v2 mixed/whitespace, all-unreadable,
      no-detection validate đúng; ID không renumber, quad/reason/score được giữ nguyên.
- [ ] Reject unknown/bool version, metadata mâu thuẫn, duplicate IDs giữa hai arrays,
      blank recognized text, invalid geometry/score, vượt profile; không bỏ extra diagnostic.
- [ ] Implement minimal version-aware snapshot; complete v1 có thể nâng internal view,
      partial v2 không downgrade mất dữ liệu; không đổi default provider.
- [ ] Chạy consumer snapshot và baseline regressions.
- [ ] Commit: `feat(ai): validate versioned OCR snapshots and preserve unreadable regions`.

## 2.2 — Issue #23: truyền uncertainty qua extraction

**Files:** `baseline.py`, `predictions.py`, `tests/unit/pipeline/test_baseline.py`,
`test_baseline_export.py`; cập nhật extraction README nếu API nội bộ thay đổi.

**Interface:** giữ business payload/FieldMetadata schema; page diagnostics giữ trong
internal snapshot và consumer report. Truyền `OCR_UNREADABLE_REGIONS`/
`SOURCE_OCR_INCOMPLETE` qua flags/issues, không nhét unreadable boxes vào field evidence.

- [ ] RED: partial/all-unreadable không thành absent; no-detection giữ unknown;
      explicit absent có evidence vẫn phân biệt được; missing label không tự gán unreadable field.
- [ ] Bảo toàn recognized text/raw candidates và detection provenance trong report;
      snapshot IDs/quads/geometry reasons/flags phải truy được sau extraction.
- [ ] Không phát sinh value/bbox/confidence từ unreadable regions; không bypass blockers
      của required fields. Bare label/value-not-located không suy thành gold obscured/absent.
- [ ] Kiểm exporter không âm thầm bỏ v2 diagnostics: giữ nguyên `vietdoc.predictions.v1`
      shape hiện tại, report diagnostics ở companion consumer report; chưa nâng wire version.
- [ ] Chạy snapshot, baseline, export và shared-schema regressions.
- [ ] Commit: `fix(ai): propagate incomplete OCR diagnostics through extraction`.

## 2.3 — Issue #23: actual evidence consumer acceptance

**Files:** new `tests/unit/pipeline/test_ocr_consumer.py`,
new `src/vietdoc/entrypoints/cli/ocr_consumer.py`,
baseline evidence callback boundary nếu repro chứng minh cần fix; không sửa AI1 evidence engine.

**Interface:** dùng callback `evidence_matcher(path, raw, context_ids) -> FieldMetadata`
hiện có; integration gọi provider `match_evidence(page, EvidenceRequest(...), prepared=...)`
và `.to_field_metadata()` qua snapshot provider tách biệt.

- [ ] Dùng dependency-free OCR types/evidence từ provider SHA pin trong integration env;
      import phải xác minh path/SHA, không dùng stale local origin ref hay download models.
- [ ] Viết tests scope đúng/sai/unscoped, repeated 90000/45000, wrapped span, partial
      page unique candidate, geometry unavailable, merged label/value không có substring bbox.
- [ ] Kiểm callback của AI2 nhận đúng field/item context; scoped partial có thể matched
      nhưng vẫn giữ incomplete flags; unscoped partial phải abstain theo provider semantics.
- [ ] Assert regions/IDs/quad/ocr_score đúng nguồn, confidence/confidence_method null;
      không dùng field path trong ví dụ AI1 để mặc định chọn row của AI2.
- [ ] Test default CI dùng tiny fixtures/callbacks, không require Paddle/GPU. Actual
      provider evidence test chạy riêng; nếu chưa chạy thì acceptance tương ứng NOT_RUN.
- [ ] Commit: `test(ai): exercise scoped OCR evidence through the AI2 consumer`.

## 2.4 — Issue #23: B0 trên native observed OCR và báo cáo chạy lại được

**Files:** new `tests/fixtures/ocr-d1-native-handoff.json` từ pinned provider,
`tests/fixtures/ocr-ai2-source.json`, `src/vietdoc/entrypoints/cli/ocr_consumer.py`,
`tests/unit/pipeline/test_ocr_consumer.py`, new
`docs/team/AI-2/2026-11-03-ocr-consumer-handoff.md`.

**Interface:** CLI mới dự kiến (chỉ chạy sau khi implementation tồn tại):
`python -m vietdoc.entrypoints.cli.ocr_consumer --provider-root <snapshot-root>
--provider-sha 7d96e93bf8315beb6fa33807231316e957671249 --output <new-output-dir>`.
CLI gọi `snapshot_page()`/`extract_baseline()` thật, tạo JSON report và exit nonzero
khi contract/acceptance assertions fail; B0 quality limitations được ghi riêng.

- [ ] Parse cả hai sample qua consumer, giữ sample_id/type, version thật, hashes,
      canonical/PreparedPage correlation. Bundle hash không thay kiểm asset bytes;
      canonical PNG chưa có thì ghi asset-byte verification NOT_RUN.
- [ ] Chạy B0 chỉ với observed `ocr`/`prepared`; test cấm đọc transcript/gold/labels
      ở inference stage và cấm sửa `sL`/`SsL`/`nộp` bằng sample-specific patches.
- [ ] Ghi payload/raw/issues/states/evidence, đúng/sai/abstain và số field attempted;
      có thể dùng gold audit ở bước đối chiếu độc lập sau inference, không làm input.
      Không gọi hai sample là benchmark hoặc full D1 quality acceptance.
- [ ] Regression receipt total expected 178000, invoice total expected 233000 nếu B0
      nhận đúng; lỗi row/header còn lại phải được báo đúng, không đổi expected để che lỗi.
      Golden partial tests tách khỏi hai native complete pages.
- [ ] Report gồm consumer/provider/base SHA, Python/dependency versions, fixture hashes,
      command/result từng case, native history vs consumer run mới, known limitations.
      Ghi rõ 2 native observed inputs, 18 not_run phía provider; không tuyên bố chạy OCR mới.
- [ ] Soạn handoff cho AI1/Backend trong repo, nêu default/migration/approval/HTTP gates
      còn mở; chưa gửi comment nếu người dùng chưa yêu cầu.
- [ ] Chạy focused consumer + baseline/export tests và full affected AI gate.
- [ ] Commit: `feat(ai): add reproducible OCR consumer report for native D1 outputs`.

## Verification và quy tắc commit cho mọi task

Các command dưới đây đã có entrypoint trong snapshot hiện tại; chạy trong đúng env,
điều chỉnh path executable theo môi trường. Đây là commands dự kiến, chưa là PASS:

```text
python -m pytest tests/unit/pipeline/test_baseline.py tests/unit/pipeline/test_baseline_export.py -q
python -m pytest tests/unit/ml/test_release_manifest.py tests/integration/api/test_compute_api.py -q
python -m pytest tests/unit/test_ci_ai.py tests/unit/test_ci_gate.py tests/contract/test_compute_contract.py -q
python -m scripts.ci.ai --allow-windows-symlink-skip --junitxml=test-results/ai.xml
python -m pip check
git diff --check
```

Linux/hosted không dùng `--allow-windows-symlink-skip`. Test modules mới chỉ chạy
sau khi đã được tạo. Sau A1 đọc lại runbook vì inventory/jobs có thể đã đổi.

- [ ] Mỗi mục: regression RED có đúng nguyên nhân → smallest fix → focused GREEN
      → inspect diff/schema compatibility/secrets/unrelated files → stage file cụ thể
      → review staged diff → commit ngay → ghi commit SHA và kết quả kiểm tra.
- [ ] Không `git add .`, không gom 10 docs dirty có sẵn. Không tạo commit cuối chứa
      tất cả thay đổi. Nếu test fail chưa giải thích được, chưa commit mục đó là hoàn tất.
- [ ] CI/config thuộc Backend: giữ patch nhỏ, liệt kê affected checks/consumer để review.
- [ ] Required hosted AI/Data/Web checks và negative fail-closed probe phải trên exact
      candidate. Vì chưa có quyền push trong task này, hosted verification để PENDING;
      local xanh không đóng R17 hoặc A1 merge gate.
- [ ] Lead review/merge và smoke develop sau merge là nghiệm thu ngoài local execution;
      không tự chuyển Issue Done/đóng R04 AI1 chỉ nhờ report này.

## Handoff dự kiến

Danh sách commit theo từng mục, exact candidate/base/provider SHA, commands/results
PASS/FAIL/SKIP/NOT_RUN, reproducible fixtures/report và các gate còn mở. Phần cứng,
model/training và runtime/provider HTTP composition tiếp tục hoãn theo yêu cầu.

## Local execution evidence

Implementation và commit ledger: [handoff 03/11](2026-11-03-ocr-consumer-handoff.md).
Các checkboxes phía trên giữ checklist gốc; hosted/Docker/Lead gates còn pending như handoff ghi rõ.
