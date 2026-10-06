# Lead

Bạn phụ trách scope, workflow, architecture, interfaces, review/merge và phối hợp giữa bốn người thực hiện. Backend/Data/AI chịu code phần của mình.

## Bắt đầu trước: chốt format để team làm song song

1. Đọc [scope](../../specs/scope.md), [business schema](../../specs/contracts/business.schema.json) và [approval policy](../../specs/approval-policy.md). Chốt receipt/invoice một trang, tiếng Việt, scalar fields và line items.
2. Kiểm ví dụ chung trong [team guide](README.md). Xác nhận tiền/quantity là string, field không thấy là null, runtime IDs và metadata nằm ngoài business payload.
3. Với Backend và hai AI, chốt OCR/extraction interfaces: text, box/quad, thứ tự đọc, image dimensions, versions, lỗi và payload đầu ra. Backend viết types; bạn review các trường và consumer xác nhận dùng được.
4. Gán mỗi vai trò cho một người cụ thể. Chưa cần mở toàn bộ backlog; giao một việc đầu tiên trong từng bản hướng dẫn.
5. Yêu cầu người nhận trả lại: hiểu input/output gì, sẽ sửa folder nào và cần ai hỗ trợ. Nếu hai người cùng sửa một interface, chọn một người implement và người còn lại review.

Bàn giao của bạn: scope/interface đã thống nhất, owner mỗi phần và acceptance của lần tích hợp đầu. Xong khi Data biết tạo nhãn nào, AI-1 biết format OCR, AI-2 biết format prediction, Backend biết nhận/lưu gì.

## Việc tiếp theo trong dự án

### Chia việc và tháo dependency

- Giao một kết quả nhỏ: ví dụ “upload được một PNG hợp lệ và trả document ID”, thay vì “làm Backend”.
- Khi provider chưa xong, cho consumer dùng fixture đã review để làm wiring; yêu cầu thay bằng provider thật trước nghiệm thu E2E.
- Có blocker thì xác định thiếu dữ liệu, thiếu contract, thiếu hardware hay lỗi code; giao đúng người giải quyết.
- Giữ Lead ở phần quyết định/review. Nếu Backend quá tải UI, giảm polish hoặc điều chỉnh nhân lực/phạm vi; không âm thầm dồn code về Lead.

### Review PR

1. Đọc task và acceptance trước, sau đó nhìn diff và kết quả checks.
2. Kiểm code ở đúng module, API không load model, pipeline/model không ghi DB, consumer không bị đổi contract bất ngờ.
3. Kiểm nghiệp vụ: missing không bịa, rerun không overwrite edits, stale save bị conflict, export đúng approved revision.
4. Với ML PR, đọc dataset/model/config version, split và dev comparison; số liệu phải có evidence và denominator rõ.
5. Với shared schema/migration/lockfile, reviewer consumer xác nhận trước; xử lý semantic conflict rồi mới merge theo dependency.

Approval cần được cấp trên nội dung cuối. Nếu tác giả sửa logic/contract sau review, kiểm lại phần bị ảnh hưởng.

### Nghiệm thu hệ thống

- Lần đầu: một receipt chạy thật qua upload → OCR → extraction → sửa → approve → JSON.
- Lần tiếp theo: invoice và line items; ngày/tiền/missing có validation đúng.
- Trước handoff: test duplicate job, worker chết, hai tab save/approve, quyền truy cập và export cũ sau rerun; model quality có report riêng.
- Model/GPU được chọn sau spike có số đo. Nếu không đạt tiêu chí, ghi phần còn thiếu và chọn bước sửa; không đổi tiêu chí để gọi là pass.

## Bạn giữ/cập nhật ở đâu?

Scope và acceptance ở `specs/`, durable decisions ở `docs/adr/`, Git Flow ở `docs/git-flow.md`; task hiện hành trong GitHub Issue/PR được Lead giao, kế hoạch ở `docs/team/`. Giữ `docs/design/v1` làm snapshot. ADR đang Proposed cần quyết định rõ khi áp dụng, không tự đổi status vì đã có scaffold.

## Ví dụ giao việc

> Backend: viết receipt/invoice typed contracts và test các JSON mẫu hiện có. Tiền/quantity phải là string; key thiếu hoặc key lạ bị từ chối. Bàn giao schema sinh từ code và test command/kết quả. AI-1/AI-2 review các types dùng chung, mình review cuối.

Bạn không cần giao lại toàn bộ phần phía sau của tài liệu khi task đầu tiên còn chưa xong.

## Cách dùng tài liệu và reviewer

Đọc [SPEC trong vùng phụ trách](../../SPEC.md) và SPEC.md trong folder con định sửa; [workflow chung](workflow.md), [Git Flow](../git-flow.md) giữ cách bàn giao. Plan này chưa phải toàn bộ task đã giao; mỗi lần Lead giao subtask, ghi issue/PR/evidence ở đó, không folder tasks. Mã hướng dẫn không phải issue ID thật.

Thứ tự bắt đầu: L1.1 → L1.2 → L2.1. Consumer liên quan review contracts/decisions; Lead duyệt cuối PR implementation. Bạn giữ các việc thiết kế/điều phối/review và nghiệm thu, không nhận coding backlog thường xuyên; yêu cầu IC bàn giao increment nhỏ để tích hợp sớm.

## Roadmap cá nhân theo tuần

Tuần tính từ kickoff. Kết quả dưới là mục tiêu cần tạo/kiểm chứng, chưa phải tính năng hiện đã chạy. Capacity giả định IC 12–16 giờ/tuần, Lead 4–8 giờ/tuần; model/hardware/profile chốt G0. W13–16 là buffer, không tự mở scope.

| Tuần | Công việc | Kết quả cần bàn giao |
|---|---|---|
| 1 | L1: scope/ownership/interfaces; consumers hiểu mẫu chung | Scope, owners và examples đã thống nhất |
| 2 | G0: model train được trong tài nguyên thật, profile/versions được ghi | G0 decision với resources/model khả thi |
| 3 | Receipt xử lý thật; AI-2 không chờ UI mới làm training | Consumer integration và merge order rõ |
| 4 | G1: receipt E2E thật; khóa tiêu chí ML sau baseline, trước mở test | Receipt E2E + pilot evidence; metric protocol |
| 5 | Dataset/test protocol cố định, provenance đủ để tái chạy | Dataset/splits/test freeze được review |
| 6 | G2: hai loại và bảng dùng được, có review; không overwrite edits | G2 hai types/items/CAS/recovery evidence |
| 7 | Handoffs evidence/confidence và review policy được kiểm chung | Evidence/confidence/review policy liên thông |
| 8 | G3: feature complete; không thêm tính năng ngoài scope | G3 feature complete; gap list |
| 9 | Đóng lỗi có repro; dừng vòng thí nghiệm không giảm lỗi | Regression/failure và bounded improvement decisions |
| 10 | G4: kiểm cả ML quality và correctness; failed gate phải báo rõ | G4 quality/correctness report |
| 11 | L4: người khác chạy được bằng hướng dẫn, không dựa máy tác giả | Clean-environment reproduction đã kiểm |
| 12 | G5: nghiệm thu và bàn giao, không tuyên bố production-ready | G5 acceptance/handoff/limitations |
| 13–16 | Không tự mở loại thứ ba; thay phạm vi/thời gian phải quyết định rõ | Đóng gaps; thay scope/time phải quyết định |

## Task chi tiết: input, bước làm, output và nghiệm thu

### L1.1 — chốt yêu cầu, tuần 1

Input: scope, business schema, approval policy và giới hạn 3–4 tháng.

1. Liệt kê chính xác receipt/invoice fields/items hiện có; ví dụ source không có buyer/address thì null, không tự thêm field loại khác.
2. Xác nhận printed/one-page/Vietnamese/30-row scope, input type người dùng chọn và dữ liệu demo fake.
3. Chốt rule prediction bất biến, edit/adopt tạo draft, approve current head và export explicit approved revision.
4. Ghi acceptance của receipt E2E và final quality; các caps/hardware targets còn cần spike phải ghi chưa đo.

Nộp: scope/acceptance được team xác nhận. Xong khi Data biết gold nào, AI biết output nào, Backend biết approval rule nào; thắc mắc còn lại có owner giải quyết.

### L1.2 — chốt owners và interfaces, tuần 1

Input: proposals của Data/AI và reference contracts.

1. Gán người thật vào bốn vai trò; không đoán username thành vị trí.
2. Backend implement shared types; AI-1 review canonical/quad/order, AI-2 review extraction/raw output, Data review labels/manifest.
3. Xác nhận thin pipeline wiring owner đề xuất là Backend. AI giữ algorithm adapters; một người sửa lockfile/migration/shared schema, các consumer review.
4. Review ít nhất một valid và invalid example mỗi boundary; chốt decimal strings, null, metadata riêng business payload, version/error conventions.
5. Quyết định ADR khi team thực sự chấp nhận, không tự đổi Proposed do có scaffold.

Nộp: owner map/interfaces và decision notes. Xong khi consumer xác nhận parse/use được ví dụ; chưa cần toàn bộ app.

### L2.1 — tháo blocker và duyệt G0, tuần 2

1. Nhận Data sample/QA, AI-1 OCR/overlay, AI-2 infer/train-step/resources/license, Backend upload/contracts.
2. Nếu thiếu hardware hoặc model OOM, yêu cầu candidate nhỏ hơn và measured alternative; không tự cấp paid API/GPU budget.
3. Xác nhận config/resource profile, train khả thi và dependency order. Accuracy 20 samples chỉ smoke, không final benchmark.
4. Giao increment tiếp theo: generator/evaluator, geometry, training loader/pilot, worker/review.

Nộp: G0 pass hoặc gap/owner/next step. Xong khi không có blocker model feasibility bị giấu dưới chữ “sẽ fine-tune sau”.

### L2.2 — nghiệm thu G1 và khóa metrics, tuần 4

1. Upload receipt fake mới trong profile; kiểm stages thật, sửa scalar/item, save, approve/export.
2. Đối chiếu export với đúng approved snapshot; yêu cầu evidence không dựa fixture/hard-coded output.
3. Đọc pilot B0/M0/M1 dev report, cùng Data/AI khóa denominators/targets trước mở final test.
4. Ghi gap và task sửa; app E2E pass và model quality là hai kết quả khác nhau.

Nộp: checklist E2E + metric protocol. Xong khi proof tái hiện được và thresholds không được chọn sau nhìn holdout.

### L3.1 — review/merge và G2/G3, tuần 5–9

1. Review từng PR với acceptance; consumer approve schema/model/migration changes. Kiểm source boundaries, tests và diff secrets/binaries.
2. Merge contracts trước providers/consumers phụ thuộc; shared migrations/lockfile không merge đồng thời mù.
3. Kiểm Data frozen split/test protocol; AI không tune final. Regression critical totals/items và failures cần report riêng.
4. Nghiệm thu invoice/items, CAS, rerun/adopt, duplicate/stale worker, evidence/null confidence.
5. Conflict semantic do tác giả giải quyết cùng consumer; Lead điều phối và re-review. Sau ba vòng không giảm lỗi, reassess thay vì train tiếp.

Nộp: gate evidence và gap list. Xong khi tính năng W8 đủ scope, không biến buffer thành feature expansion.

### L4.1 — final gate/handoff, tuần 10–12

1. Khóa candidate/evaluator/data hashes, cho Data mở final protocol; đọc support/per-type/slices và failures.
2. Quality không đạt phải ghi gap/buffer/limitation, không sửa target để pass. Correctness invariants phải pass độc lập.
3. Cho người khác chạy clean app/inference/train subset; kiểm restore/rollback và sample privacy.
4. Demo two types/invalid input/stale save/rerun/export cũ, bàn giao với limitations và các quyền publish/deploy cần yêu cầu riêng.

Nộp: acceptance report, decision và handoff. Bạn không nhận coding backlog thường xuyên; owner viết fix/tests phần họ.

## Git Flow cho Lead

1. Nhận một subtask/acceptance từ Lead; tạo hoặc dùng issue thật, branch feature/bug từ develop theo [Git Flow](../git-flow.md). Không push trực tiếp main/develop.
2. Sửa đúng ownership ở trên; shared contract/lockfile/migration cần báo owner/consumer trước. Không stage datasets/weights/secrets/runtime hoặc unrelated edits.
3. Chạy focused checks thật, inspect diff, ghi command/config/versions/input-output mẫu và limitations. Chưa có check executable thì ghi phần chưa xác minh; không tự báo CI pass.
4. PR đích develop, peer reviewer theo mục reviewer, Lead duyệt cuối. Tác giả không tự approve; đổi logic/contract sau approval cần review lại.
5. Conflict: tác giả đọc cả hai thay đổi cùng consumer, merge origin/develop vào branch đã chia sẻ, không force-push hoặc chọn ours/theirs toàn file. Chạy lại checks sau resolve.
6. Sau merge, consumer smoke trên develop; issue ghi evidence rồi mới Done. Release main/hotfix theo quy trình riêng, không suy ra quyền deploy từ task.

Lead điều phối merge order và semantic conflict, không nhận viết code thay owner. Branch protection/required checks là policy cần xác minh, không coi đã bật chỉ vì tài liệu có ghi.

## Checklist bàn giao

- Code/output thực, input/output đúng contract và version/manifest rõ.
- Consumer chạy được sample, tests/report/commands thực và failed cases có sample IDs.
- Không raw dataset/weights/secrets/PII/runtime trong diff; không hard-coded demo output thay inference.
- Peer review/Lead review nội dung cuối, post-merge smoke và limitations đã ghi.
- Gate/quality targets dùng [workflow chung](workflow.md), không tự đổi ngưỡng sau mở final test.


## Khi có blocker, giao ai?

| Hiện tượng | Người kiểm đầu | Việc cần yêu cầu |
|---|---|---|
| Gold không khớp ảnh/label chưa rõ | Data | QA/correction history và dataset version mới |
| OCR sai dấu/số, boxes lệch | AI-1 | Sample repro, raw/canonical/processed overlay, before/after |
| OCR đúng nhưng payload sai/rows trộn | AI-2 | B0/M0/M1 diff, raw prediction và field/row error |
| Model không load/train được | AI-2 | Hardware/memory/config, alternative feasible và trade-off |
| Job stuck/duplicate/rerun overwrite | Backend | State/fence/outbox trace và regression test |
| Hai bên hiểu schema khác nhau | Lead điều phối; Backend sửa types | Consumer examples và compatibility check trước merge |

Bạn giữ quyết định và review; người sở hữu phần lỗi viết fix và tests của họ.
