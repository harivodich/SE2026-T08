# AI Engineer 1 — Preprocessing, OCR và geometry

Bạn phụ trách preprocessing ảnh đầu vào, geometry, OCR và evidence nguồn. Bạn nhận ảnh/PDF và bàn giao canonical page cùng chữ/vị trí để AI-2 trích field, Backend highlight. OCR dùng engine tiếng Việt pretrained trước; fine-tune extractor thuộc AI-2.

## Bắt đầu trước: preprocessing tối thiểu và OCR trên 20 mẫu

1. Review OCR contract cùng Backend/AI-2: canonical image/dimensions, ordered blocks, block IDs, text, quad, score, OCR version và lỗi.
2. Chọn một pretrained OCR engine có hỗ trợ tiếng Việt để smoke; PaddleOCR adapter là hướng thiết kế hiện tại. Pin package/model version đã chạy được, không dựa mặc định latest.
3. Đọc PNG/JPEG đúng channel order/dtype/range và EXIF orientation; PDF một trang được render thành canonical image trong Python ai-service với resource limits đã thống nhất.
4. Trả mỗi vùng chữ: block ID, text, bốn điểm quad trong [0,1] và engine score. Trả page index 0, image dimensions và version rõ ràng.
5. Chạy trên 20 sample, lưu OCR result gắn sample ID. So với transcript/region gold của Data; ghi sample nào sai dấu, mất số, đảo thứ tự hoặc boxes lệch.
6. Bàn giao adapter gọi được và vài output thực theo contract; report latency/config/hardware, lỗi runtime và giới hạn đã gặp.

Xong khi engine thực sự chạy, output parse/type được, người nhận dùng được text/geometry; các lỗi nhận dạng được report. Không yêu cầu OCR hoàn hảo ở task đầu tiên và không biến fixture giả thành kết quả engine.

## Cải thiện preprocessing sau baseline đo được

- Thử deskew/contrast nhẹ bằng cùng bộ dev; so trước/sau, chỉ giữ bước giúp ích có evidence.
- Canonical image là ảnh viewer hiển thị. Nếu OCR đọc trên ảnh preprocess khác, lưu inverse transform và map boxes về canonical coords.
- Kiểm rotation/crop/resize và quad order bằng ảnh/geometry fixtures. Geometry không xác định thì ghi unavailable, không vẽ box đoán.
- Giữ text/row order phù hợp ngôn ngữ và table layout; mô tả xuống dòng không được ghép sang sản phẩm khác.
- Xử lý ảnh không đọc được, engine crash, timeout và resource lỗi bằng typed outcomes; không trả OCR fake để job thành công.

## Evidence cho từng field

AI-2 trích value; bạn viết mapper liên kết value đó tới OCR blocks. Match cả label/context/geometry để phân biệt khi `45.000` xuất hiện ở line total và total chung.

Bàn giao source regions và block IDs cho field paths, report ambiguity/coverage. Cùng Backend kiểm viewer highlight trên đúng canonical page. OCR score chỉ là score vùng chữ; field correctness confidence do AI-2 calibration, không copy score OCR thành probability.

## Code và nơi lưu output

| Nơi | Bạn sở hữu |
|---|---|
| `src/vietdoc/pipeline/preprocess.py` | Xử lý ảnh có config/version |
| `src/vietdoc/pipeline/geometry.py` | Canonical/inverse coordinate transforms |
| `src/vietdoc/pipeline/ocr/port.py`, `paddle_adapter.py` | OCR interface/engine adapter |
| `src/vietdoc/pipeline/evidence.py` | Match prediction với source blocks |
| `tests/unit/pipeline/`, `tests/fixtures/` | Geometry/OCR boundary fixtures và checks |

AI-1 implement Python OCR/page types theo shared schema/proposal; Backend implement Java DTO tương ứng. Hai phía validate cùng fixtures, không import types qua ngôn ngữ. Data owns evaluator chung; bạn hỗ trợ OCR/geometry correctness definitions. Output chạy lớn ở `artifacts/evaluation/`, không commit hàng loạt ảnh/OCR text.

## Kiểm tra trước PR

- Có chữ tiếng Việt có dấu, số tiền nhỏ, ảnh xoay/nghiêng, blank/corrupt image và PDF nhiều trang ngoài profile.
- Canonical boxes hữu hạn và trong bounds; overlay không lệch sau preprocessing.
- Adapter không load engine mỗi request nếu đã có loader lifecycle; đo memory/latency, giải phóng resources phù hợp.
- AI-2 chạy được extractor consumer từ OCR result; Backend highlight được một sample thực.
- Pin engine/model/version và ghi command/config đã chạy, output mẫu, limitations.

Ví dụ: OCR đọc `3`, `15.000`, `45.000` và vị trí của chúng. Việc xác định `45.000` là total hay dòng hàng được extractor/evidence phối hợp giải quyết, không tự gán tất cả số lớn nhất là total.

## Cách dùng tài liệu và reviewer

Đọc [SPEC trong vùng phụ trách](../../src/vietdoc/pipeline/SPEC.md) và SPEC.md trong folder con định sửa; [workflow chung](workflow.md), [Git Flow](../git-flow.md) giữ cách bàn giao. Plan này chưa phải toàn bộ task đã giao; mỗi lần Lead giao subtask, ghi issue/PR/evidence ở đó, không folder tasks. Mã hướng dẫn không phải issue ID thật.

Thứ tự bắt đầu: O1.1 → O1.2 → O1.3 → O2.1/O2.2. Reviewer: AI-2 review OCR input; Backend review canonical/evidence contract; Lead duyệt boundary. Giữ một task coding chính đang làm, bàn giao increment nhỏ; không chờ hoàn tất cả vai trò mới tích hợp.

## Roadmap cá nhân theo tuần

Tuần tính từ kickoff. Kết quả dưới là mục tiêu cần tạo/kiểm chứng, chưa phải tính năng hiện đã chạy. Capacity giả định IC 12–16 giờ/tuần, Lead 4–8 giờ/tuần; model/hardware/profile chốt G0. W13–16 là buffer, không tự mở scope.

| Tuần | Công việc | Kết quả cần bàn giao |
|---|---|---|
| 1 | O1: canonical/preprocess tối thiểu; proposal OCR, smoke | Input/geometry proposal và OCR smoke |
| 2 | O1–O2: OCR thật, overlay, CER sample | OCR thật/overlay/CER + runtime evidence |
| 3 | O2: order/table/geometry; O4: evidence đầu tiên | Geometry/order và evidence consumer đầu tiên |
| 4 | O3: đo trước/sau deskew/chữ nhỏ | Preprocess before/after trên dev |
| 5 | O3: stress transforms, repeated values | Adversarial transforms và regression fixtures |
| 6 | O4: evidence trên hai types, lỗi OCR khó | Evidence hai types và OCR errors có repro |
| 7 | O4: source highlight, score/ambiguity features | Viewer highlight/ambiguity score features |
| 8 | O5: pin OCR/preprocess/geometry versions | Pinned OCR/preprocess/geometry/evidence versions |
| 9 | O5: memory/latency và OCR failure suite | Stress/error/performance report |
| 10 | O5: phân tích OCR cuối, không tune theo test | Final OCR analysis; không tune holdout |
| 11 | O5: tái chạy inference trên máy sạch | Inference/overlay reproduction commands |
| 12 | Hỗ trợ demo/fix lỗi có repro | Handoff config/versions/limitations |
| 13–16 | Fix hard OCR có evidence | Hard OCR fixes có repro và regression checks |

## Task chi tiết: input, bước làm, output và nghiệm thu

Folder: `src/vietdoc/pipeline/preprocess.py`, `geometry.py`, `ocr/`, `evidence.py`; tests unit/contract/fictional fixtures. AI-2 fine-tune extractor; AI-1 không mặc định fine-tune OCR.

### O1.1 — thống nhất ảnh chuẩn và input, tuần 1

Dependency và effort dự kiến: L1.2/B1.2/D1 samples; 3–4h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: D1 samples, B1.2 compute/page proposal, file/resource scope; xem [private compute protocol](../../specs/contracts/compute-api.md).

1. Chốt canonical là ảnh viewer sau EXIF orientation/PDF render, page=0 và dimensions rõ.
2. Ghi channel order/dtype/range engine cần; phân biệt original/canonical/processed image.
3. Thống nhất quad point order/coordinates/normalization, inverse transform và unavailable outcomes cùng Backend/AI-2.
4. Chốt admission của Backend và compute decode/render limits cùng policy; không tự đọc arbitrary file path từ request.

Nộp: input/geometry examples, Python types và proposal để Backend viết Java DTO. Xong khi viewer/extractor cùng hiểu một box và orientation.

### O1.2 — loader và preprocessing tối thiểu, tuần 1–2

Dependency và effort dự kiến: O1.1; 6–8h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Decode JPEG/PNG, xử lý EXIF; PDF không mã hóa một trang render trong Python ai-service dưới byte/page/pixel/time limits đã review.
2. Convert color space/dtype/range đúng OCR, canonical dimensions giữ rõ; resize riêng processed nếu cần.
3. Trả PreparedPage/compute artifacts theo B1, transform processed→canonical; reject corrupt/unsupported/out-of-profile bằng typed errors.
4. Test blank/corrupt/rotated/oversized/multipage; không crop/deskew nâng cao trước baseline.

Nộp: loader/preprocess code/tests/config, vài canonical/processed pairs. Xong khi supported samples đọc được, failure không fake success, geometry consumer dùng được.

### O1.3 — OCR engine adapter thật, tuần 1–2

Dependency và effort dự kiến: O1.2/D1.2; 6–10h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Chọn pretrained Vietnamese OCR candidate theo thiết kế, pin/audit engine+model revisions đã smoke; không assume latest/default đúng model.
2. Loader lifecycle giữ engine trong Python ai-service process, không Java web API. AI-2 compose lifecycle theo M2.3. Gọi OCR trên prepared images, chuyển vendor output sang common types.
3. Xuất block IDs/text/quad/score/read order/page/dimensions/versions; không sinh fake text/score khi engine fail.
4. Chạy D1 thật và gửi OCR JSON cho AI-2 consume. Ghi cold load/warm latency/memory/hardware và các lỗi.

Nộp: OCR port/adapter/config, actual outputs và report. Xong G0 khi AI-2 parse dùng được, engine chạy thật, failed samples report đầy đủ.

### O2.1 — geometry correctness và overlays, tuần 2–3

Dependency và effort dự kiến: O1.2/O1.3; 6–8h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Unit tests identity/resize/rotate/crop mapping và round-trip điểm với tolerance đã định nghĩa.
2. Map quads processed→canonical, normalize về [0,1], finite và bounds; missing transform đánh dấu unavailable.
3. Overlay boxes lên canonical image, kiểm ảnh xoay/crop/resize và label/row tại vị trí thật.
4. Kiểm reading order cho Vietnamese/columns/description wrap; giữ enough blocks để extractor group rows.

Nộp: geometry tests/overlay và order cases. Xong khi test/consumer overlay đúng; không vẽ guessed box để che transform thiếu.

### O2.2 — OCR error baseline, tuần 2–3

Dependency và effort dự kiến: O1.3/D3.1; 4–6h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Chạy D3 evaluator trên transcript gold, per-type/clean/skew/small-text slices.
2. Gom errors dấu/số/missing/order/geometry/runtime theo sample IDs; lưu OCR version/config.
3. Cùng AI-2 chấm ảnh hưởng total/items; không chỉ báo CER trung bình.
4. Chọn hypothesis preprocessing cho O3, không tune final holdout.

Nộp: OCR report/errored samples và hypothesis. Xong khi Lead/Data tái tính được metric từ outputs, denominator không bị drop failures âm thầm.

### O3.1 — cải thiện preprocessing, tuần 4–6

Dependency và effort dự kiến: O2.2 measured dev errors; 8–12h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Chọn một lỗi có evidence, thử một thay đổi: deskew/contrast/resolution/noise handling.
2. Giữ cùng engine/evaluator/dev inputs, chạy before/after; measure CER/WER, extraction totals/items, memory/time.
3. Lưu transforms/version/config, regression tests clean/skew/wrap; không làm mất source rồi giữ gold như đọc được.
4. Giữ bước tốt theo trade-off; không cải thiện thì revert riêng thay đổi của task và ghi kết luận, không làm hỏng dữ liệu người khác.

Nộp: preprocessing increment + before/after report. Xong khi có measured improvement hoặc quyết định loại bỏ có lý do, canonical overlay vẫn đúng.

### O4.1 — source evidence matcher, tuần 3–7

Dependency và effort dự kiến: O2.1/M2.1/M2.2; 8–12h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: AI-2 raw values/field paths, OCR blocks và canonical geometry.

1. Tìm candidates bằng text/label/context/row location; số lặp phải phân biệt line total/document total.
2. Map `/total_amount` hoặc item paths sang blocks/regions, giữ ambiguity/coverage flags.
3. Không tìm được thì source regions rỗng/unavailable theo contract; không dùng arithmetic tạo bbox/value.
4. Test repeated values/wrap/null/missing transform; cung cấp score/ambiguity features cho AI-2, không tự gọi OCR score là field correctness.
5. Cùng Backend click field/item và kiểm highlight đúng canonical image.

Nộp: evidence mapper/tests/coverage và viewer integration sample. Xong khi match đúng hoặc báo uncertainty, consumer dùng được.

### O5.1 — freeze/stress/reproduction, tuần 8–12

Dependency và effort dự kiến: O3.1/O4.1/M2.3/M6.1; 8–12h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Freeze OCR/preprocess/geometry/evidence versions, AI-2 pin training/inference đúng transformations.
2. Stress corrupt/blank/skew/PDF-outside-profile/resource timeout; typed errors/lifecycle cleanup, không infinite retry.
3. Đo cold/warm latency/memory thật; support Data final analysis nhưng không tune theo test.
4. Bàn giao engine/model/config/commands và fake sample overlay để người khác tái chạy trên môi trường sạch.

Nộp: frozen manifests/tests/performance/limitations. Xong khi consumer smoke pass và output không phụ thuộc hidden local config.

## Git Flow cho AI-1 — Preprocessing/OCR

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
