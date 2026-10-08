# VietDoc — workflow team, Git Flow và nghiệm thu

## 1. Cách bắt đầu

Đọc [spec folder](../../specs/repository-layout.md), [scope](../../specs/scope.md) và doc của [vai trò mình](README.md). Roadmap theo tuần và 49 task chi tiết nằm trong năm doc cá nhân; file này chỉ giữ workflow/handoffs/gates dùng chung.

Repo hiện là scaffold, chưa có API/OCR/model/UI chạy. Kế hoạch 12 tuần và buffer 13–16 tính từ kickoff; capacity giả định mỗi IC 12–16 giờ/tuần, Lead 4–8 giờ/tuần; Backend đề xuất16–20h/tuần W1–4 để nhắm G1, nếu không đủ dời gate/dùng buffer. AI-2 dành4–8h W2–3 cho M2.3, giữ fine-tune pilot. Lead xác nhận capacity/hardware/scope/owner trước giao task. Task đang làm theo GitHub Issue/PR hoặc phiếu giao việc trực tiếp, không dùng folder tasks. Không tự tạo toàn bộ issues hôm nay.

## 2. Workflow của một task từ giao đến xong

1. Lead chọn một task nhỏ, gán người, input/version đang có, acceptance, reviewer, dự kiến mốc và ngoài phạm vi. Chỉ mở issue hiện cần làm; không tạo folder tasks hoặc copy backlog dài; tiến độ nằm trong issue/PR hiện hành.
2. Người nhận đọc task/specs/owning module, ghi dependency thiếu. Nếu provider chưa có implementation, consumer dùng tiny fictional fixture đúng contract để test wiring; không báo fixture thành inference thật.
3. Tạo branch từ develop theo [Git Flow](../git-flow.md), cập nhật trước khi bắt đầu. Một task/PR, stage file cụ thể. Không đưa raw data, weights, secrets hoặc runtime vào Git.
4. Viết increment nhỏ chạy được, tests cho behavior/boundary liên quan, command/config thực đã chạy. Không chỉ nộp notebook output hoặc TODO module nếu task yêu cầu code dùng được.
5. Tự kiểm acceptance, input/output mẫu, diff, compatibility và failures. ML/data task phải ghi manifest/model/evaluator/code versions.
6. Gửi PR theo quyền workflow được giao, peer reviewer đúng consumer kiểm trước, Lead duyệt cuối. Consumer chạy lại sample thay vì chỉ đọc chữ “đã test”.
7. Sửa review trên branch task, chạy lại checks; đổi contract/logic cần review lại. Lead merge theo dependency, không chọn ours/theirs cả file khi có semantic conflict.
8. Sau merge consumer chạy smoke trên develop; ghi evidence và limitations rồi mới gọi task Done. Việc bị blocked phải nêu ai cần cung cấp gì, không chỉ “đang chờ”.

Một gói bàn giao tối thiểu gồm code/config, command đã chạy, manifest/version, input/output fake mẫu, test/report result, lỗi còn biết, consumer và PR/task reference. Outputs lớn local ignored; báo cáo đưa Git phải loại secrets/PII và absolute private paths.

Dependencies trong cards có hai loại: proposal/fixture (có thể gửi partial early để unblock) và runnable artifact/gate (phải có trước nghiệm thu). B1.2/O1.1/D1.2 không cần chờ nhau Done toàn bộ; thống nhất một geometry example rồi triển khai song song. M6.1 freeze candidate trước D5.1 holdout; final report D5.1 chỉ là input bước model-card/handoff cuối M6.1, không tạo dependency cycle. D2.2 gửi pilot v0.1 trước full dataset v1 để M3.1/M3.2 bắt đầu.

## 3. Workflow bàn giao giữa người với người

### Data → AI-1

Data gửi sample IDs, images/canonical dimensions, transcript/regions/visibility, manifest/version/hash. AI-1 đọc vài sample và đối chiếu overlay/labels; vấn đề nhãn trả Data sửa/version, không tự dùng OCR thành gold.

### Data → AI-2

Data gửi train/dev manifests, gold/statuses, grouping/labels coverage và data card. AI-2 verify rồi build model batches; không random-resplit hoặc đặt unlabeled=null. Final manifest freeze, quyền mở predictions theo Lead protocol.

### AI-1 → AI-2

AI-1 gửi OCR blocks/order/quads/scores/page dimensions/versions/transforms và actual sample outputs. AI-2 adapter thử parse, chạy B0/M0; token/row overflow báo explicit. Failure do OCR có sample repro gửi AI-1; extraction sai khi OCR đúng thuộc AI-2.

### AI-1/AI-2 → Backend

AI-2 gửi private HTTP service (M2.3), actual responses/errors/attempt assets/manifests, AI-1 OCR/canonical qua service này. Java client dùng shared schema/fixtures; runner pin manifest/remaining budget và kiểm fence before completion. Viewer page theo run/revision; unavailable không guessed.

### Backend → Lead

Gửi runnable E2E, PR/diff, focused tests, OpenAPI/migrations, UI fake screenshots và failures. Lead tự đi qua scenario và snapshot/version checks; documents/UML không thay app proof.

### AI-2 → Data → Lead

AI-2 gửi frozen predictions/model manifest, Data chấm evaluator frozen và report per-type/slice/support/failures, Lead duyệt gate. Tránh tác giả model tự chọn subsets đẹp và bỏ failed runs. Holdout fail cần báo, không tune rồi claim cùng test untouched.

## 4. Lịch thực hiện đầu tiên, theo buổi làm việc

Buổi là thứ tự công việc, không cam kết mỗi buổi đủ xong nếu capacity khác. Tuần 1–2 chỉ cần giao các bước này; các task sau chọn khi input đủ.

| Buổi | Lead | Data | AI-1 | AI-2 | Backend |
|---|---|---|---|---|---|
| 1 | L1.1 scope/fields và owners | D1.1 dictionary/fake gold | O1.1 geometry proposal | M1.1 hardware/model/license | B1.1 Java DTO/schema fixtures |
| 2 | L1.2 review interface examples | D1.2 render vài sample đầu | O1.2 loader/canonical | M1.2 load/infer smoke | B1.2 compute/page contract |
| 3 | Giao dependency/blocker cụ thể | D1.2 đủ 20 và QA/manifest | O1.3 OCR thật/outputs | M1.3 train step; M2.3 serving shape; M2.1 rules nhỏ | B1.3 app/checks, B2.1 storage/ownership |
| 4 | L2.1 đọc G0 evidence | D2.1 generator, D3.1 evaluator cases | O2.1 overlays, O2.2 metrics | M2.1/2 actual OCR baseline/normalizer | B2.2 upload, B3.1 job service |
| Sau G0 | Chốt model/config và việc tuần 3–4 | D2.2 v0.1, D3 report | O2/O3 geometry/preprocess | M2.3 actual HTTP + M3 loader/pilot | B3.2 Java runner/client, B4/B5 receipt review/UI |

Không bắt Data đợi app để render, AI-2 đợi full OCR để smoke/train step, hoặc Backend đợi fine-tune mới làm review. Wiring fixtures được phép trong development, E2E nghiệm thu phải actual providers.

M2.3 phụ thuộc B1.2/O1.3/M2.1, không chờ full fine-tune. B3.2 nghiệm thu private HTTP thật; B4/B5 có fixture khi phát triển nhưng G1 actual provider. Busy503 và Java retry phải giữ single GPU slot.

## 5. Git Flow thực hành

Policy đầy đủ ở [Git Flow](../git-flow.md). Mỗi doc cá nhân có mục Git Flow/reviewer; đoạn dưới là quy trình chung. Main giữ bản ổn định, develop tích hợp; feature/bug đi qua PR, hotfix từ release tag khi có release thật.

### Trước khi tạo branch

Kiểm status/root/remote, bảo toàn edits. Chỉ switch/pull khi working tree sạch hoặc thay đổi của bạn đã được lưu an toàn trên branch đúng; không tự stash/reset/clean để vượt lỗi. Nếu develop local chưa có, làm hướng dẫn tracking ở policy.

Ví dụ Git dưới là lệnh người thực hiện chạy khi task/commit/push đã được giao quyền, chưa được thực thi bởi lượt sửa docs:

```powershell
git status --short --branch
git remote -v
git fetch origin
git switch develop
git pull --ff-only origin develop
# Thay SE-123 bằng issue ID thực; slug viết snake_case.
git switch -c feature/SE-123_receipt_contracts
```

### Làm và bàn giao PR

1. Implement subtask, focused checks và inspect diff. Stage từng file đúng task, không git add toàn repo.
2. Commit trên branch task bằng local identity đã xác nhận; push branch task theo quyền được giao, PR target develop.
3. PR ghi issue/mã hướng dẫn, acceptance, affected paths/consumer, commands/check results, input-output/version/hash, risks và phần chưa verified. Tác giả không tự approve.
4. Peer reviewer đúng ownership kiểm trước, Lead duyệt cuối; required checks thực sự có phải pass. Nếu chưa có CI/runtime thì task B1.3 tạo checks; không ghi CI pass giả.
5. Branch đã push/chia sẻ thì merge origin/develop vào branch, không rewrite/force-push; resolve semantic conflicts cùng owner, rerun checks, re-review logic đổi.
6. Lead merge sau review, consumer smoke trên develop và issue ghi evidence. Delete branch task khi merge theo policy, không main/develop.
7. Release develop→main chỉ sau gates, tested artifact/tag theo policy; không push trực tiếp main, tự deploy hay bật protection ngoài quyền task.

Branch protection/required checks/invitations/access trên GitHub chưa được kiểm tra lại trong lượt audit local này. Chính sách docs không là bằng chứng settings đã bật. Mã D/O/M/B/L trong guide không phải issue đã tạo; tiến độ ở issue/PR đang làm.

## 6. Gate phải có bằng chứng gì?

### G0 — cuối tuần 2: khả thi dữ liệu và model

- Data bàn giao 20 sample integration và generator prototype; gold parse được, consumer dùng được.
- AI-1 chạy OCR thật trên samples, xuất text/boxes và overlay đúng canonical image; ghi lỗi/latency/memory.
- AI-2 chạy load/infer và ít nhất một train step; ghi model/processor revisions, memory, thời gian, output-validity và license. Nếu không khả thi, thử candidate nhỏ hơn trước full training.
- Backend có contracts/tests và upload slice; công việc app không bị chặn bởi việc chọn model.
- Lead xác nhận hardware/profile và phương án, không hứa accuracy từ 20 samples. Không chạy full training nếu chưa qua train-step/memory gate.

### G1 — cuối tuần 4: một receipt xuyên suốt

1. Upload sample fake hợp lệ, chọn receipt, tạo job nền.
2. Java runner gọi Python service dùng preprocessing/OCR thật và baseline hoặc model adapter thật. Fixture chỉ dùng test wiring, không thay inference để nghiệm thu.
3. Người dùng nhìn canonical image, sửa một scalar và một item, save tạo revision mới.
4. Approve đúng revision có total, đủ xác nhận/warning acknowledgements, export JSON khớp snapshot.
5. AI-2 có fine-tune pilot và báo cáo dev ban đầu; Data/Lead khóa metric definitions và targets trước mở final test.

Model pilot có thể còn lỗi. Receipt E2E pass không chứng minh model quality pass; hai báo cáo tách nhau.

### G2/G3 — tuần 6/8: đủ chức năng hai loại

- Receipt và invoice có fields/items đúng schema, editor dùng được, missing/ambiguous được hiển thị.
- Evidence có coverage/ambiguity report; unavailable thì UI báo rõ.
- Hai tab save cùng version: chỉ một lần thành công; request stale trả 409 và UI giữ edits.
- Rerun tạo candidate; adopt tạo draft revision mới; head người dùng không bị thay âm thầm.
- Duplicate/retried compute không tạo hai committed runs; stale attempt không commit.
- Confidence có calibration report khi đủ support; thiếu support dùng null/flags. Không autoapprove.

### G4 — tuần 10: quality và correctness

Targets từ [data/evaluation design](../design/v1/06-data-ml-evaluation.md), còn cần Lead/team xác nhận sau baseline W4:

| Chỉ tiêu | Target lập kế hoạch | Cách báo cáo |
|---|---|---|
| Raw JSON validity | ≥98% | Trước repair/human edit; sample count và failures |
| Present scalar normalized EM | ≥85% mỗi type | Không tăng score nhờ nhiều absent/null |
| Total amount EM | ≥95% | Receipt/invoice riêng; missing/false fill riêng |
| Matched-row cell accuracy | ≥85% | Kèm unmatched/duplicate rows để tránh che mất hàng |
| Exact-row accuracy | ≥75% | Row matching policy versioned |
| Fine-tune so baseline | Critical total trên dev không thấp hơn baseline | B0/M0/M1 cùng evaluator và preprocessing; so cả latency/memory |
| Business correctness | Các invariants bắt buộc pass | Approval/CAS/rerun/export/ownership/fencing tests |

Final holdout dự kiến 200–400 base documents tổng hai loại; report unseen families/independent mock riêng. Targets chưa phải kết quả hay cam kết production. Nếu không đạt: ghi gap, nguyên nhân và bước sửa/buffer; không chỉnh ngưỡng sau khi nhìn test để gọi là pass. Nếu test đã dùng để tune, cần protocol/test version mới và ghi hạn chế.

### G5 — tuần 12: bàn giao tái lập

- Người khác chạy ứng dụng trên môi trường sạch bằng commands đã kiểm chứng.
- Dữ liệu có generator/manifest/splits/hash/data card; model có config/checkpoint/processor/manifest/model card; evaluator có version và reports.
- Có demo hai types, invalid input, stale save, rerun và export approved cũ.
- Có danh sách hạn chế: synthetic-to-real gap, unreadable inputs, geometry/evidence coverage, confidence support và tài nguyên.
- Raw dataset/weights/private runtime không nằm trong Git. Deploy/publish không tự được cấp quyền bởi gate này.

## 7. Checklist đánh dấu task Done

- Mục tiêu trong task đã có code/output thực; không chỉ kế hoạch, TODO hoặc screenshot notebook.
- Input/output đúng shared contract, version/manifest rõ, consumer gọi/đọc được.
- Test/command/report thực đã chạy, normal/invalid/boundary cases liên quan; số liệu chưa đo ghi rõ.
- Artifact lớn local ignored, diff không secrets/PII/weights/datasets/unrelated changes.
- Peer reviewer và Lead review nội dung cuối theo Git Flow; shared schema/migration consumer không bị bỏ sót.
- Consumer smoke sau merge, limitations/blockers còn biết được ghi; không gọi mọi task là Done vì hết tuần.

Một báo cáo mẫu cấu trúc, chưa phải kết quả thật:

```text
Task: O1.3 / <issue ID thực nếu đã mở>
Trạng thái: Ready for review hoặc Blocked (ghi đúng)
Code/PR: <link thực>
Input versions: <manifest + OCR/page contract>
Command/config/hardware: <đã chạy gì, ở đâu>
Outputs: <OCR artifacts + sample IDs + versions>
Checks: <test names + actual results>
Consumer check: <AI-2/Backend đã thử gì, actual result>
Known failures: <sample IDs + nguyên nhân hoặc chưa rõ>
Next action / need from: <việc cụ thể và người cần hỗ trợ>
```

Quality targets/data-size targets là mục tiêu cần Lead/team chốt sau baseline trước mở final test. Workflow không đổi scope/ADR status hoặc tự giao toàn bộ backlog.
