# Backend Engineer — API, lưu trữ và UI tối giản

Bạn đưa các phần Data/OCR/extraction thành ứng dụng có upload, xử lý nền, review, approve và export. Team chưa có frontend engineer riêng, nên bạn cũng làm viewer/editor cơ bản theo scope.

## Bắt đầu trước: typed contracts và tests

1. Đọc [reference schemas](../../specs/contracts/README.md), [API design](../design/v1/03-contracts.md) và OCR proposal của AI-1.
2. Viết typed models trong `src/vietdoc/contracts/`: receipt/invoice/line items, OCR/page/block, extraction input/raw/result, field metadata/issues, review DTO, job states/message và errors.
3. Generate JSON Schema từ models khi có code. Giữ một source-of-truth; reference files được đồng bộ, không viết lại hai hệ types khác nhau mãi.
4. Test payload hợp lệ hai loại, null/money strings, missing/unknown keys, wrong type/schema, items limit, bbox bounds và broker message chỉ chứa IDs/version.
5. Bàn giao types + valid/invalid fixtures; AI/Data consumers thử parse. Lead review shared fields và constraints trước merge.

Xong khi contract rõ và consumers dùng được cùng format. Hỗ trợ fixtures để integration trong lúc model chưa xong; result fixtures không dùng để báo AI accuracy.

## Sau contracts: upload và persistence

1. Tạo app/dependency wiring, SQLAlchemy session/UoW và Alembic lineage; environment/config có bounds, secrets không commit.
2. Implement user auth/ownership theo profile demo; kiểm document/run/revision/page/export access qua document owner.
3. Implement `POST /api/v1/documents`: multipart file + type, 201 metadata. Kiểm streaming size, format/decoder, page/pixel/profile; file corrupt/oversize trả error rõ.
4. Lưu original private asset bằng server-generated key/hash. DB failure không được làm mất trace của orphan asset; cleanup có registry/bounds.
5. Implement list/detail/canonical page stream. Browser không đọc file system hoặc arbitrary object paths trực tiếp.

## Job và nối pipeline

1. `POST /api/v1/documents/{id}/jobs` tạo job + outbox trong transaction, trả 202; không chạy inference nặng trong route.
2. Dispatcher publish job ID; worker claim/heartbeat, đọc pinned manifest, gọi pipeline do AI bàn giao.
3. Completion service kiểm lease/fence, ghi một immutable run/job, update state/audit. Initial result chỉ tạo head draft nếu document chưa có head.
4. `GET /api/v1/jobs/{id}` trả state/stage/error; worker crash/transient errors có bounded retry/recovery. OOM/model-load/output-invalid không retry vô hạn.
5. Rerun terminal job tạo job/run mới; document đã có head nhận candidate, không overwrite edits.

## Review, approve và export

1. Implement revision list/get/save. Save nhận full payload, base revision, expected document version và reason; append revision + CAS head + audit cùng transaction.
2. Stale request bị conflict; UI giữ local edits. Không last-write-wins hoặc sửa payload revision in-place.
3. Implement adopt-run riêng với cùng version/head guard; candidate trở thành draft revision mới.
4. Approve current revision, revalidate đúng payload, yêu cầu review confirmation và warning acknowledgement. Total phải non-null; blockers không được bypass.
5. Export explicit approved revision thành business JSON. Cùng revision/format/exporter version cho cùng bytes/hash; draft mới không thay export cũ.
6. Audit actor/time/action/base/new revision/reason; logs chỉ IDs/stage/duration/error, không raw documents/OCR hoặc secrets.

## UI phải dùng được

- Danh sách: type, job state, head review state; upload và mở detail.
- Detail: canonical image zoom/pan; field editor; items grid thêm/sửa/xóa; issue panel; evidence highlight khi có.
- Save/Approve/Export đúng policy server; hiển thị lỗi và version conflict bằng lời dễ hiểu.
- Rerun result là candidate có nút adopt; history chỉ rõ revision được approve/export.
- Generate API types từ OpenAPI khi API ổn định; polling status đủ cho bản đầu.

UI không tự gán confidence hoặc quyết định approval rules; khi source region unavailable thì báo không có vùng nguồn thay vì vẽ box đoán.

## Code bạn sở hữu

`contracts/`, `identity/`, `documents/`, `jobs/`, `review/`, `exports/`, `infrastructure/`, `entrypoints/`, `migrations/`, `web/`, `infra/` và CI. Theo phân công tích hợp đề xuất ở [team guide](README.md), bạn viết lớp nối mỏng `pipeline/service.py`; hai AI bàn giao adapters và review cách gọi. Không duplicate thuật toán AI hoặc business rules giữa route và task.

## Nghiệm thu trước bàn giao

- Một receipt thật chạy từ upload đến export; sau đó thêm invoice/table.
- Invalid file/profile, owner khác, missing total và unapproved export bị từ chối đúng specs.
- Hai tab save cùng version: một success, một conflict; save/approve race cùng invariant.
- Duplicate delivery chỉ một committed run; stale worker không commit; outbox/recovery đóng commit/publish gap.
- Rerun không overwrite approved/user-edited head; export cũ vẫn đúng snapshot.
- Fresh environment có commands/config đã chạy, dependency lock phù hợp, health/readiness, backup/restore và rollback instructions khi implementation đủ.

Bàn giao: runnable source, OpenAPI/examples, migrations, UI screenshots trên mẫu giả, focused checks đã chạy, config/runbook và limitations. Lead nghiệm thu hệ thống; hai AI review integration, Data xác nhận sample labels.

## Cách dùng tài liệu và reviewer

Đọc [SPEC trong vùng phụ trách](../../src/vietdoc/SPEC.md) và SPEC.md trong folder con định sửa; [workflow chung](workflow.md), [Git Flow](../git-flow.md) giữ cách bàn giao. Plan này chưa phải toàn bộ task đã giao; mỗi lần Lead giao subtask, ghi issue/PR/evidence ở đó, không folder tasks. Mã hướng dẫn không phải issue ID thật.

Thứ tự bắt đầu: B1.1 → B1.2/B1.3 → B2.1/B2.2 → B3.1. Reviewer: Lead review nghiệp vụ; AI review inference/geometry integration; Data xác nhận fixtures. Giữ một task coding chính đang làm, bàn giao increment nhỏ; không chờ hoàn tất cả vai trò mới tích hợp.

## Roadmap cá nhân theo tuần

Tuần tính từ kickoff. Kết quả dưới là mục tiêu cần tạo/kiểm chứng, chưa phải tính năng hiện đã chạy. Capacity giả định IC 12–16 giờ/tuần, Lead 4–8 giờ/tuần; model/hardware/profile chốt G0. W13–16 là buffer, không tự mở scope.

| Tuần | Công việc | Kết quả cần bàn giao |
|---|---|---|
| 1 | B1: types/tests; app/CI tối thiểu | Shared types/tests và app runnable tối thiểu |
| 2 | B2: upload/ownership/private storage; B3: job wiring | Upload/private storage/ownership + job wiring |
| 3 | B3: worker gọi stages thật; B4–B5: review/viewer đầu tiên | Worker actual providers; viewer/review draft |
| 4 | B4–B5: sửa/approve/export receipt; invoice smoke | Receipt edit/approve/export E2E + invoice smoke |
| 5 | B4–B5: invoice/items; CAS và warning guards | Invoice/items/editor và CAS/warnings |
| 6 | B3/B6: outbox/recovery/duplicates; table workflow | Outbox/recovery/duplicate tests + G2 |
| 7 | B4–B6: rerun/adopt/history; ownership/race tests | Rerun/adopt/history + owner/race checks |
| 8 | B6: cancel/recovery và export history | Feature complete/cancel/export history |
| 9 | B6: load/failure tests, logs, readiness | Load/failure/logging/readiness evidence |
| 10 | B7: release candidate, restore rehearsal | Release candidate/restore rehearsal |
| 11 | B7: runbook/rollback, UI/demo hoàn thiện | Runbook/rollback và clean-env reproduction |
| 12 | B7: E2E clean environment | Two-type E2E handoff |
| 13–16 | Reliability/performance/presentation buffer | Reliability/performance/presentation fixes theo gap |

## Task chi tiết: input, bước làm, output và nghiệm thu

Folder: `src/vietdoc/contracts/`, `identity/`, `documents/`, `jobs/`, `review/`, `exports/`, `infrastructure/`, `entrypoints/`; `migrations/`, `web/`, `infra/`, CI và thin stage wiring đề xuất. Một Backend chịu cả UI tối giản; Lead cần kiểm capacity ở mỗi gate.

### B1.1 — business contracts/tests, tuần 1

1. Implement receipt/invoice/line-item types theo schema, decimal strings/null/keys/30 rows; không đổi domain để hợp model.
2. Test valid/invalid/unknown/missing keys/type/schema mismatch và date/money conventions với owning validators.
3. Generate schema từ code và đồng bộ reference, không maintain hai type systems khác nhau.
4. Data/AI-2 thử parse fixtures, Lead review fields/rules.

Nộp: business types/schema/tests và tiny fictional examples. Xong khi consumers dùng được và contracts không import FastAPI/ORM/Celery/model frameworks.

### B1.2 — page/OCR/extraction/job contracts, tuần 1–2

1. Review O1.1 và M1 input proposal; implement PreparedPage/OCR blocks/raw prediction/pipeline result/errors cần slice đầu.
2. Geometry/order/dimensions/versions rõ; payload business tách metadata/runtime IDs, run/job IDs do application tạo.
3. Job message chỉ IDs/version, state/error typed; review DTO/head/version thêm lúc triển khai slice liên quan.
4. Test bounds/finite/unknown keys/type mismatches, provider/consumer same fixtures; version changes có reviewer affected.

Nộp: shared types/boundary tests. Xong khi hai AI có interface implement adapters mà không import ORM/API framework.

### B1.3 — app/config/checks tối thiểu, tuần 1–2

1. App/dependency composition/config thực dùng, health endpoint không load weights; Python/runtime theo repo.
2. Dependency groups/lock sau smoke, ML runtime không bị import nặng trong API; AI review cần pin gì.
3. CI focused formatting/unit/contract checks từ commands đã chạy, permissions tối thiểu, không thêm workflows giả.
4. `.env.example` chỉ variables dùng, secrets local ignored. Commands install/start/check ghi sau verification.

Nộp: runnable app/config/lock/checks. Xong khi app khởi động và checks chạy trong môi trường kiểm chứng, không chỉ scaffold.

### B2.1 — persistence/ownership/private storage, tuần 2–3

1. Tạo SQLAlchemy/UoW/Alembic cho increment hiện dùng; FK/head parent document constraints và unique invariants cần review.
2. Auth demo/seed fake users theo thiết kế; owner check trên document/page/run/revision/export.
3. Private storage key server-generated, paths safe/hash/size; không dùng filename làm filesystem path.
4. Test second user không đọc asset/history/export; migrations upgrade clean/existing DB, staging cleanup bounded/registry.

Nộp: storage/auth/repositories/migrations/tests. Xong khi services authorize mọi object và no public raw-data folder.

### B2.2 — upload/list/detail/canonical page, tuần 2–3

1. Upload multipart + selected receipt/invoice type; bytes/signature/decode/one-page/pixel limits, encrypted/corrupt handling.
2. Persist original metadata/private asset, phối hợp O1 canonical renderer dưới cùng bounds; transaction failure không mất orphan trace.
3. List/detail/page authorized API, 201 upload; browser không nhận arbitrary object paths.
4. Tests valid image/PDF, oversize/wrong type/multipage/path attacks/ownership; limits khóa G0, không invent benchmark.

Nộp: APIs/OpenAPI/examples/tests. Xong khi sample upload/read được qua authorized services, no inference blocking in route.

### B3.1 — job lifecycle/create/outbox, tuần 2–3

1. Define queued/running/retry/terminal transitions, active-job uniqueness/idempotency theo thiết kế.
2. Create job+outbox cùng transaction, pin pipeline/model manifest, trả 202; message IDs only.
3. Claim/heartbeat/lease/fence và complete/fail services, bounded attempts/deadline; DB giữ state authority.
4. Test duplicate create/claim/terminal reclaim và rollback/unique boundaries ngay khi viết.

Nộp: lifecycle/job services/migrations/tests. Xong khi job không chạy trong API và duplicate không tạo active inference vô kiểm soát.

### B3.2 — worker và thin compute pipeline, tuần 3–4

1. Composition root inject adapters O1/M2, call preprocess/OCR/extraction/normalization/evidence/confidence, không duplicate algorithms.
2. Worker claim→compute→complete, attempt artifacts riêng lease token; loader lifecycle theo measured GPU/CPU profile.
3. Completion fence/unique run/job, immutable prediction, initial draft chỉ nếu head null; existing head nhận candidate.
4. Test wiring bằng fixtures, nghiệm thu bằng actual OCR/extraction receipt G1. Raw/execution errors typed, no fake success.

Nộp: runnable worker/pipeline/output storage/completion tests. Xong khi receipt compute thật và late/duplicate completion không ghi sai head/run.

### B3.3 — dispatcher/recovery/cancel, tuần 3–8

1. Dispatcher publish outbox/mark delivery, retry/reconciliation có bounds, publish duplicate an toàn.
2. Expired lease/queued no claim → recover theo DB, stale tokens không commit; Redis delivery không là business truth.
3. Classify transient/permanent/OOM/invalid output, không retry endless; status/error APIs actionable.
4. Cancel theo lifecycle guards, late completion bị chặn khi không còn quyền commit; heartbeat/resources cleanup.
5. Tests commit/publish gap, duplicate delivery/worker kill/late complete và cancel race theo policy.

Nộp: dispatcher/recovery/cancel/config/tests. Xong khi failures recover hoặc fail rõ có giới hạn; một committed run/job, không claim exactly-once execute.

### B4.1 — review get/save và CAS, tuần 3–4

1. Get trả immutable prediction, head revision/version/payload/metadata. Save full payload+base head/expected version/reason.
2. Revalidate input, append revision, CAS document head/version và audit cùng transaction, rollback khi stale.
3. Giữ revision cũ/prediction bất biến; stable row IDs là editor metadata, không model-generated business values.
4. Test hai saves cùng version: một success/một 409, không orphan revision/audit; different-owner/document IDs reject.

Nộp: review APIs/service/tests. Xong khi sửa không last-write-wins và consumer giữ được edits khi conflict.

### B4.2 — approve và approved export, tuần 4–5

1. Approve current head/version, revalidate snapshot, non-null/unambiguous total, no blockers, review confirmation/warning acknowledgement.
2. Transaction approval+version CAS+audit, save/approve race serialize; frontend button không là authority.
3. Export explicit approved revision, stable bytes/hash cùng exporter version; latest draft trả conflict, chọn approved cũ được.
4. Test missing total/unapproved/blocked/unknown owner, save-vs-approve, repeated export checksum và approved snapshot unchanged.

Nộp: approval/export APIs/tests. Xong G1 khi receipt sửa/approve/export thật, G2 thêm invoice/items; no admin bypass ngầm.

### B4.3 — rerun/adopt/history, tuần 5–7

1. Rerun tạo job/run mới, không thay head đã sửa/approve.
2. Show candidate/run history; adopt CAS append draft revision mới, preserve old revisions/approvals.
3. Save sau approval cũng tạo draft; export approved cũ vẫn same snapshot/hash.
4. Test rerun complete sau edits và adopt/save race, selected run cùng document/owner.

Nộp: candidate/adopt/history APIs/tests. Xong khi người dùng chọn thay kết quả có chủ ý, model không tự ghi đè.

### B5.1 — upload/list/viewer/status UI, tuần 2–4

1. UI upload/type/list/detail, polling job stage/error; dùng API types/fixtures theo contract lúc API chưa xong.
2. Viewer canonical zoom/pan, no direct storage paths, auth/expiry errors rõ.
3. Evidence overlay O4 khi có, missing regions báo unavailable; không vẽ guessed box.
4. Nối actual APIs/provider trước E2E, test fake receipt/invoice và failures.

Nộp: runnable web slice/screenshots/focused checks. Xong khi người khác upload/xem output thực, không chỉ mock UI.

### B5.2 — fields/items/review controls UI, tuần 3–7

1. Editor scalar/items add/edit/delete, keep decimal strings/null, description wrap; không zero-fill absent.
2. Issues/warnings/review confirmation controls gửi đúng server policy/version/revision; no client-only approval rules.
3. Save conflict giữ local edits, compare/reload/reconcile version có chủ ý; không auto-resubmit ghi đè.
4. Approve/export explicit revision, rerun candidate/adopt/history rõ, confidence limitations hiển thị đúng.
5. Test operator sửa field+row rồi export bằng UI, stale tab/rerun flow; screenshot fake data only.

Nộp: editor/history UI và E2E evidence. Xong khi không cần SQL/manual DB sửa để demo; Backend giữ UI giản dị để đủ capacity.

### B6.1 — failure/security/resource/performance checks, tuần 6–9

1. API chết sau commit, dispatcher chết sau publish, Redis message loss, worker kill/expired fence, DB outage completion: inject theo failure matrix.
2. Ownership trên page/run/revision/export; logs IDs/stage/time/error, no secret/raw payload/OCR/PII.
3. Input/resource bounds và permanent failure retries, storage missing/actionable error, no arbitrary URL fetch/tool execution.
4. Measure API responsive during inference, queue caps/age, cold/warm model memory/latency, health/readiness/heartbeat. p95 cần nhiều measured observations và hardware rõ.
5. Focused unit/integration/E2E + migration compatibility, inspect actual test evidence và unresolved failures.

Nộp: failure/concurrency/security-boundary tests và measured report. Xong khi invariants pass; không trì hoãn CAS/idempotency design đến task này mới nghĩ.

### B7.1 — clean environment, backup/restore/rollback và handoff, tuần 10–12

1. Nhận frozen pipeline/model manifests O5/M6, pin runtime/config, activation theo Lead gate; old jobs pin old release.
2. Backup DB+storage manifest, restore rehearsal kiểm FK/hashes/approved export; không destructive DB rollback.
3. Runbook thực: setup/config/migrate/seed/start/smoke/stop/rollback từ commands đã chạy, no secrets.
4. Người khác chạy clean environment two types/invalid/stale/rerun/export cũ, screenshots/tests/report.
5. Handoff app/OpenAPI/migrations/UI/locked env/artifact locations/limitations; raw dataset/weights/runtime không Git, deployment cần quyền riêng.

Nộp: release candidate/runbook/restore/reproduction evidence. Xong G5 khi app không phụ thuộc hidden local state máy tác giả.

## Git Flow cho Backend

1. Nhận một subtask/acceptance từ Lead; tạo hoặc dùng issue thật, branch feature/bug từ develop theo [Git Flow](../git-flow.md). Không push trực tiếp main/develop.
2. Sửa đúng ownership ở trên; shared contract/lockfile/migration cần báo owner/consumer trước. Không stage datasets/weights/secrets/runtime hoặc unrelated edits.
3. Chạy focused checks thật, inspect diff, ghi command/config/versions/input-output mẫu và limitations. Chưa có check executable thì ghi phần chưa xác minh; không tự báo CI pass.
4. PR đích develop, peer reviewer theo mục reviewer, Lead duyệt cuối. Tác giả không tự approve; đổi logic/contract sau approval cần review lại.
5. Conflict: tác giả đọc cả hai thay đổi cùng consumer, merge origin/develop vào branch đã chia sẻ, không force-push hoặc chọn ours/theirs toàn file. Chạy lại checks sau resolve.
6. Sau merge, consumer smoke trên develop; issue ghi evidence rồi mới Done. Release main/hotfix theo quy trình riêng, không suy ra quyền deploy từ task.

Một PR giải quyết một kết quả nhỏ; các outputs lớn ở local ignored, chỉ manifests an toàn/tiny fictional fixtures/reports đã review được đưa Git.

## Checklist bàn giao

- Code/output thực, input/output đúng contract và version/manifest rõ.
- Consumer chạy được sample, tests/report/commands thực và failed cases có sample IDs.
- Không raw dataset/weights/secrets/PII/runtime trong diff; không hard-coded demo output thay inference.
- Peer review/Lead review nội dung cuối, post-merge smoke và limitations đã ghi.
- Gate/quality targets dùng [workflow chung](workflow.md), không tự đổi ngưỡng sau mở final test.
