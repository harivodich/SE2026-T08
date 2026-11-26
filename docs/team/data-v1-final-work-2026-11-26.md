# Data — phần việc còn lại đến V1

Đây là nhiệm vụ tiếp theo, thay phần dependency cũ đã được xử lý trong gói bàn
giao 26/11. Không phải yêu cầu làm lại PR88 hoặc sinh lại D22. Những finding chưa
đóng trong review cũ vẫn phải đối chiếu bằng test/evidence, không bỏ qua vì có
task mới. Làm trên branch riêng từ develop sau khi Lead merge PR hỗ trợ.

## Đầu vào đã chuẩn bị

- `pilot-inputs.zip` và `transfer.json`: snapshot `v0.2-pilot-20261126`, seed
  20261126, 40 base/160 variants; train 20 base/80 variants, dev tương tự;
  receipt/invoice mỗi loại 4 families, mỗi family 5 base; 0/1/3/12/30 hàng.
- Sáu assets/mẫu, manifest, records bốn trạng thái, canonical rerender và receiver
  verification. Không có final assets. Renderer thực là Pillow 12.0/font đã pin;
  không coi môi trường Data pin cũ là đã tái tạo đúng byte của snapshot này.
- Bản review AI của 40 ảnh clean, 410 cặp nghi ngờ, witnesses nội dung và lineage;
  reviewed plan riêng. Bản pending ban đầu được giữ nguyên để truy vết. Bản AI
  review là đề xuất cho Lead duyệt trong PR, không giả chữ ký con người.
- Native OCR và reader/token receipts của chính population này được đóng gói
  trong bộ bàn giao chung. OCR score không phải correctness của field.
- D22 B0/M0/M1 predictions/dev report đã có để thử evaluator. M0/M1 chưa đạt
  quality; tuyệt đối không dùng các prediction này làm gold hoặc final benchmark.

Xem inventory/hash và phạm vi từng receipt trong `role-unblock-acceptance-2026-11-26.md`.

## D1 — Tiếp nhận và khóa dữ liệu làm việc

1. Verify pin `transfer.json` nhận từ Lead, archive SHA và receiver fresh-root bằng
   `python -m vietdoc.data.pilot_packet verify --bundle PACKET --output NEW_ROOT`.
   Hash tự nhất quán chỉ chứng minh integrity; đối chiếu pin ngoài archive.
2. So manifest/records/labels: đủ 160 IDs, 960 assets, 40 base; không đổi family,
   source/assignment groups, variants hoặc split. Dùng reviewed plan đúng manifest.
3. Đối chiếu source review ban đầu và reviewed supplement; ghi quyết định nhận
   của Lead theo PR merge thật. Không gán Lead/AI1/AI2 approval bằng tên tự điền.
4. Giữ `present/absent/obscured/unlabeled`. Nguồn synthetic hiện có 0 unlabeled
   là số support thực, không sửa obscured thành absent để tăng số train.

**Đạt:** receipt nhận đủ inputs, không có sample bị bỏ không ghi lý do; có lệnh
verify chạy được trên checkout sạch. Commit một increment input acceptance.

## D2 — Đóng evaluator bằng oracle độc lập

1. Đọc evaluator hiện hành và task cũ; không tự thay metric khi chưa chốt authority.
2. Thêm/hoàn thiện tests cho receipt/invoice, decimal strings/null, thiếu/thừa ID,
   duplicate ID/key, sai schema/type/dataset hash, failed/missing/truncated
   prediction. Mẫu failed/missing vẫn nằm trong denominator tương ứng.
3. Dùng bảng tay nhỏ có expected counts tính độc lập: scalar EM, total critical,
   missing/false-fill, table row matching, insert/delete/duplicate rows và OCR
   CER/WER theo protocol đang có. Không lấy hàm implementation tính expected.
4. Với obscured/unlabeled, kiểm eligibility theo từng field/cell và báo support;
   không coi null gold là mọi trạng thái unknown. Khi support bằng 0 phải in N/A.
5. Test reorder rows, repeated amounts/descriptions, fractional quantity, 0 hàng,
   30 hàng, Unicode/NFC, dấu thập phân và VND. Dữ liệu invalid phải reject hoặc
   có failure accounting rõ, không score như gold hợp lệ.

**Đạt:** oracle/regression chạy được, metric definitions và denominator khớp
report; mỗi lỗi evaluator sửa kèm regression. Commit theo từng cụm metric.

## D3 — Data/label/geometry QA tự chạy

1. Đóng QA cho hashes, RGB/uint8/HWC, kích thước, quad, transcript order và PDF/PNG
   của cùng sample; lỗi clipping/overflow phải dừng, không drop âm thầm.
2. Test variants cùng base/source/template luôn cùng split; source alias/exact
   content/exact PNG collision phải bị chặn. dHash tương tự chỉ tạo candidate,
   không tự chứng minh duplicate hoặc distinct.
3. Test archive traversal, symlink/reparse, duplicate/casefold/Windows aliases,
   corrupt member, size/count caps, partial extraction cleanup và existing root.
4. Tạo QA command nhận path/pins, trả JSON + exit code ổn định; tái dùng producer,
   receiver, label adapter hiện có, không làm một bộ validator song song.

**Đạt:** fixture tốt pass, mỗi corruption tương ứng fail closed; công khai phiên
bản renderer/font; QA không cần chờ AI2 model. Commit QA/regression coherent.

## D4 — Report công bằng trên dữ liệu đã lộ

1. Re-score predictions D22 đang có bằng evaluator đã kiểm. Đối chiếu nguyên nhân
   nếu số liệu khác báo cáo 26/11, không sửa số cho khớp.
2. Báo per-type, base/family, quality/row slices, raw/normalized schema riêng,
   failed/missing/false-fill/critical total và table end-to-end. Không chọn chỉ
   normalized schema để che raw serving reject.
3. Phân biệt variant count với số base độc lập; confidence interval/limitations
   phải phản ánh grouping. Không so hai candidate trên membership khác nhau.
4. Viết runner nhận một hoặc nhiều prediction files và manifest pin; kiểm
   provenance trước score. Chạy ngay với dữ liệu/prediction đã cung cấp, không
   cần đợi AI2 train mới để hoàn thành code và kiểm evaluator.

**Đạt:** report tái lập, bảng coverage và failure IDs đầy đủ; kết quả không phải
final acceptance. Commit runner/report template và tiny fictional fixtures.

## D5 — Chuẩn bị final protocol để nhận candidate tự động

1. Khóa trước metric/threshold/slices/custodian và điều kiện mở final theo specs
   đã được Lead chốt. Nếu policy chưa có giá trị cụ thể, báo thiếu quyết định;
   không tự invent threshold hoặc đánh dấu Proposed ADR thành Accepted.
2. Runner phải đòi candidate/config/source/model/OCR/evaluator/schema/manifest
   hashes và kiểm file thật; final gate từ chối mutable/missing/mismatched pins.
3. Không mở historical final để phát triển. Kiểm positive/negative protocol bằng
   tiny fictional non-final fixtures và thử với D22/pilot đã lộ.
4. Sau khi AI2 phát hành candidate frozen, job nhận artifact chạy cùng runner;
   không còn phải đợi Data viết thêm code hoặc trả lời mapping. Kết quả cuối
   vẫn phải chạy thật, không được ghi trước PASS trong task.

**Đạt:** một lệnh kiểm protocol và một lệnh score đã thử; candidate thật là input
release sau này, không phải blocker cho D1–D4 hoặc việc viết runner.

## Bàn giao và Definition of Done

- PR vào develop, từng commit gắn thay đổi có nghĩa + test; không chia commit
  hình thức. Không commit raw data/weights/runtime/cache/PII.
- Gửi bảng task cũ → file/test/receipt mới, commands/exit/results, versions/hashes,
  support/exclusions và remaining limitations. CI xanh trên head cuối.
- Không tự đổi schema, split, labels, metric hoặc tự dùng final. Mọi finding P1
  thật phải sửa; P2 không ảnh hưởng increment có thể tách issue có acceptance.
- Không chờ AI1/AI2 để thực hiện D1–D4. Final run chỉ nhận frozen artifacts bằng
  runner đã hoàn chỉnh; nếu model chưa đạt quality, ghi release gate chưa đạt.
