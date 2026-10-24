# Data Engineer

Bạn chuẩn bị dữ liệu, đáp án đúng và cách chia tập; đồng thời giữ evaluator độc lập để biết OCR/extraction sai ở đâu. Hai AI cần dùng đúng cùng dataset version và metric rules.

## Bắt đầu trước: 20 tài liệu giả để team tích hợp

Input: [business schema](../../specs/contracts/business.schema.json), ví dụ trong [team guide](README.md) và scope tiếng Việt một trang.

1. Tạo 10 receipt và 10 invoice, ít nhất hai template mỗi loại. Đây là bộ thử tích hợp, chưa phải final test để báo chất lượng model.
2. Tạo tên cửa hàng/công ty/người mua, ngày, giá và hàng hóa giả. Không dùng thông tin cá nhân, chữ ký/con dấu thật.
3. Với mỗi sample, tạo ảnh và business gold JSON từ cùng data object. Invoice dùng đầy đủ key riêng của invoice; không đổi tên key theo dataset bên ngoài.
4. Thêm các tình huống: thiếu địa chỉ/giờ/buyer, vài dòng hàng, mô tả xuống dòng, số tiền có dấu phân cách và hai số giống nhau trên ảnh.
5. Đọc lại ảnh đã render, đối chiếu từng field/row. Ghi transcript text đúng cho OCR; boxes gold theo canonical image nếu renderer cung cấp. Không lấy OCR/model output làm gold.
6. Ghi sample ID, type, template/family/base ID, schema version, seed, relative asset paths và hash vào manifest. Ghi label status riêng: present/absent/obscured/unlabeled; không trộn metadata này vào business payload.

Bàn giao: 20 ảnh, 20 gold JSON, transcripts và manifest; tiny fictional subset cho tests. AI-1 nhận ảnh/transcript/geometry; AI-2 nhận ảnh/gold; Backend nhận mẫu để upload và review UI.

Xong khi mọi gold JSON có schema đúng, ảnh đọc được và khớp đáp án; consumer tìm sample bằng ID và biết label nào chưa annotate. Mẫu integration có thể được team xem chung, không gọi chúng là untouched holdout.

## Sau bộ mẫu: generator và dataset tái lập

1. Viết generator receipt/invoice, đổi bố cục/label vocabulary/table arrangement thật sự; font/màu khác chưa đủ thành layout family mới.
2. Sinh ảnh/PDF một trang cùng JSON/transcript/evidence; lưu seed, generator version và sample lineage.
3. Thêm rotation/blur/noise có mức giới hạn. Nếu crop làm mất field, cập nhật visible-label/evidence hoặc status; không để gold đòi đọc nội dung đã biến mất.
4. Viết data validation: JSON/schema, Unicode, corrupt images, ngày/tiền, trùng IDs/hash, row count và gold overflow/clipping.
5. Chia train/dev/final test theo template family trước khi sinh values. Mọi augmentation cùng base nằm cùng split; kiểm near-duplicates giữa các tập.
6. Freeze final-test manifest/hash trước khi AI dùng test; dev dùng để tune. Dataset target và số families theo [data plan](../design/v1/06-data-ml-evaluation.md), điều chỉnh cùng Lead sau hardware/model spike.

## Dataset public

- Audit nguồn tải, terms/license, ngôn ngữ, PII và label coverage trước khi dùng.
- ReceiptVQA chỉ có QA supervision cho những câu được annotate; không tự coi là full receipt JSON hoặc full-page OCR transcript.
- Adapter map nhãn vào format chung và giữ source IDs. Nếu hai nguồn dùng cùng ảnh, group cùng split để tránh leakage.
- Ghi data card: nguồn, version, phạm vi labels, exclusions và limitation. Nguồn không qua audit thì loại khỏi core dataset.

## Evaluation bạn phụ trách

1. Viết evaluator so prediction với gold sau cùng normalization; giữ dấu tiếng Việt, ngày/tiền đúng convention.
2. Report mỗi type: field correctness, total/date, missing field, false fill, row/cell và unmatched/duplicate rows. Không gộp score để che type khó.
3. OCR CER/WER chỉ tính ở sample có transcription gold; hai AI giúp định nghĩa/check metric, không lấy QA answer làm transcription.
4. So baseline và model trên cùng dataset/evaluator; count cả failed jobs và support của từng slice. Final test chỉ chạy theo lịch freeze của Lead.
5. Xuất vài sample lỗi có ID, gold/pred và nhóm nguyên nhân để AI sửa trên dev. Final-test results không dùng tune tiếp nếu chưa lập protocol test mới.

## Code và bàn giao

| Nơi | Nội dung cần viết khi nhận việc |
|---|---|
| `src/vietdoc/data/generator/` | Sinh values/templates/rendered labels |
| `src/vietdoc/data/manifest.py`, `validation.py`, `splits.py` | Manifest, QA và split |
| `src/vietdoc/data/adapters/` | Dataset adapters đã audit |
| `src/vietdoc/evaluation/` | Evaluator/metrics/reports, hai AI review |
| `datasets/raw/`, `processed/` | Dữ liệu lớn local, ignored |
| `datasets/manifests/` | Manifest an toàn, versioned |

Bàn giao mỗi dataset version: manifest/hash, counts theo type/family/field, seed/config và command đã chạy, cách lấy dữ liệu, lỗi còn biết. Raw data nằm ngoài Git; chỉ tiny fictional fixtures được review mới vào `tests/fixtures/`.

Ví dụ: trên ảnh chung có `45.000`, gold lưu `"45000"`. Nếu ảnh không có buyer thì gold buyer null với status absent; nếu chưa annotate buyer trong nguồn public thì status unlabeled và không chấm trường đó.

## Cách dùng tài liệu và reviewer

Đọc [SPEC trong vùng phụ trách](../../src/vietdoc/data/SPEC.md) và SPEC.md trong folder con định sửa; [workflow chung](workflow.md), [Git Flow](../git-flow.md) giữ cách bàn giao. Plan này chưa phải toàn bộ task đã giao; mỗi lần Lead giao subtask, ghi issue/PR/evidence ở đó, không folder tasks. Mã hướng dẫn không phải issue ID thật.

Thứ tự bắt đầu: D1.1 → D1.2 → D2.1; D3.1 khi có gold. Reviewer: AI-1/AI-2 review data/evaluator; Lead duyệt schema/split/metric/gate. Giữ một task coding chính đang làm, bàn giao increment nhỏ; không chờ hoàn tất cả vai trò mới tích hợp.

## Roadmap cá nhân theo tuần

Tuần tính từ kickoff. Kết quả dưới là mục tiêu cần tạo/kiểm chứng, chưa phải tính năng hiện đã chạy. Capacity giả định IC 12–16 giờ/tuần, Lead 4–8 giờ/tuần; model/hardware/profile chốt G0. W13–16 là buffer, không tự mở scope.

| Tuần | Công việc | Kết quả cần bàn giao |
|---|---|---|
| 1 | D1: 20 mẫu fake, gold/transcript/manifest | 20 ảnh/gold/transcripts/manifest đã QA |
| 2 | D2: generator/split prototype; D3: evaluator fixtures | Generator/split prototype và tiny evaluator cases |
| 3 | D2: thêm families; D3: report B0/M0 | Families/gold QA + B0/M0 report |
| 4 | D2: dataset v0.1; D3: baseline/dev report | Dataset v0.1 và dev report cho pilot |
| 5 | D2: dataset v1, freeze final manifest; D4: independent mock | Dataset v1 + frozen final manifest/hash |
| 6 | D3: row/cell report, QA lỗi labels | Table labels/row metrics và label corrections |
| 7 | D3: coverage/correctness labels cho calibration | Calibration correctness labels/coverage |
| 8 | D3: evaluator freeze, dev report | Frozen evaluator và per-type dev report |
| 9 | D4: independent mock QA/stress slices | Independent mock/stress QA |
| 10 | D5: chạy holdout đóng băng, report mỗi type | Final holdout report/support/failures |
| 11 | D5: data card/lineage/tái tạo subset | Data card/lineage/tái tạo subset |
| 12 | Đóng gói reports/fixtures an toàn | Handoff manifests/generator/evaluator/reports |
| 13–16 | Bổ sung dữ liệu độc lập nếu cần | Data độc lập bổ sung theo protocol nếu cần |

## Task chi tiết: input, bước làm, output và nghiệm thu

Folder: `src/vietdoc/data/`, `src/vietdoc/evaluation/`; dữ liệu lớn ở ignored `datasets/raw/`, `datasets/processed/`.

### D1.1 — data dictionary và fake values, tuần 1

Dependency và effort dự kiến: L1.1 + schema; 3–4h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: business schema và L1.1, không chờ API hoàn thiện.

1. Với từng field ghi nghĩa, source label examples, raw format/canonical format, absent/obscured/unlabeled status.
2. Receipt gồm merchant/date/time/total/items; invoice gồm number/date/seller/buyer/subtotal/tax/discount/total/items theo schema.
3. Sinh fake merchant/seller/buyer/date/values/products có dấu; tiền/quantity canonical strings. Không real PII/identifiers/signatures/stamps.
4. Tạo row data cùng description/quantity/unit/unit_price/line_total, không gán hết quantity=1 hoặc mọi total cùng mẫu.

Nộp: dictionary/config và vài gold JSON valid có receipt/invoice. Xong khi AI/Backend hiểu raw/canonical và null statuses; Lead review scope.

### D1.2 — render 20 integration samples, tuần 1

Dependency và effort dự kiến: D1.1/O1.1/B1.2; 6–8h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: D1.1 và page/geometry proposal B1.2/O1.1.

1. Làm ít nhất hai layout mỗi type, sinh 10 receipt/10 invoice; render ảnh từ chính data object tạo gold.
2. Thêm missing optional fields, nhiều rows, description wrap, repeated amounts, dấu phân cách tiền.
3. Xuất gold/transcript và regions nếu renderer cung cấp; đọc ảnh để QA từng field/row, font dấu/clipping.
4. Ghi sample/base/family/type/schema/seed/version/path/hash và label status vào manifest; variants cùng base giữ lineage.
5. Chọn tiny fictional subset cho tests; bộ lớn không commit. Gửi mẫu ngay khi vài sample QA xong, không chờ toàn bộ generator.

Nộp: 20 samples + gold/transcripts/manifest, QA notes. Xong khi schema valid, gold khớp ảnh và consumer load được; bộ này được nhóm nhìn chung, không untouched holdout.

### D2.1 — generator tái lập và validation, tuần 2–3

Dependency và effort dự kiến: D1.2; 8–12h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Tách values/templates/render để cùng seed/config/version tạo cùng output theo reproducibility policy.
2. Thêm test Unicode/font/rows 0/1/30/overflow, ngày/tiền/missing; schema/ID/hash/path/image validation.
3. Render image/PDF one page và transcript/regions từ cùng object; không lấy OCR output làm gold.
4. Viết report exclusion/rejected samples và reason; lỗi nhãn phải sửa generator/version chứ không chỉnh theo prediction.

Nộp: generator/validator code/config/tests và sample manifest tái chạy. Xong khi fresh run tìm được cùng IDs/gold/hashes theo policy, labels không overflow đã biết chưa xử lý.

### D2.2 — families, augmentation và split, tuần 3–5

Dependency và effort dự kiến: D2.1/G0; 12–18h chia PR. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: D2.1, OCR/extraction errors trên dev và capacity G0.

1. Tạo layout families khác spatial structure/label vocabulary/table arrangement; đổi font/màu chưa thành family mới.
2. Assign family/source/base groups vào train/dev/final trước sinh values; variants cùng base không qua split.
3. Add bounded skew/blur/noise; crop che field cập nhật visibility/evidence, unreadable là failure slice riêng.
4. Dedupe hashes và near-duplicate/content groups; report ambiguous groups để review.
5. Target mỗi type 10 families: 6 train/2 dev/2 final, 3.000–6.000 clean base documents tổng hai types sau G0; số thật theo capacity, không đếm variants độc lập.
6. W4 bàn giao v0.1 đủ pilot; W5 freeze v1/final manifest/hash, dev-calibration tách khi support đủ.

Nộp: split/generator configs, manifests/hash và counts per type/family/status/quality/rows. Xong khi no overlap/leakage, AI-2 loader dùng được; targets thiếu phải báo trước freeze.

### D3.1 — evaluator scalar và OCR, tuần 2–4

Dependency và effort dự kiến: D1.2/O1.3/M2.1; 6–10h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: gold D1, prediction artifacts B0/M0, normalization policy AI-2, OCR conventions AI-1.

1. Tạo tiny cases với score biết trước: đúng hết, sai value, null present, false fill absent, unlabeled.
2. Chấm present normalized exact match/F1; không strip dấu tiếng Việt. Wrong value theo policy FP và FN, missing/false fill báo riêng.
3. Ghi denominator/support/exclusions; failed predictions không biến mất khỏi E2E report.
4. CER/WER chỉ trên transcript gold, không dùng QA answers như toàn trang; version Unicode/tokenization/normalization rules.
5. Test expected scores của tiny cases, để hai AI kiểm conventions trước report thật.

Nộp: evaluator/tests, definitions/version, B0/M0 report với sample errors. Xong khi tiny cases đúng kỳ vọng, score không phình nhờ absent/unlabeled.

### D3.2 — evaluator bảng/evidence và comparison, tuần 4–8

Dependency và effort dự kiến: D3.1/M3.2/O4.1; 8–12h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Khóa row matching policy với cases wrap/reorder/duplicate/missing; không chỉ zip rows theo thứ tự.
2. Report matched cell accuracy/exact-row cùng unmatched/duplicate counts; số tiền/quantity/unit riêng khi phù hợp.
3. Evidence/text-association/geometry chỉ chấm gold regions có annotation; ghi coverage/ambiguity.
4. Chạy B0/M0/M1 cùng dataset/preprocess/evaluator, per-type/slice. Gửi dev-calibration correctness labels cho AI-2 theo protocol.
5. W8 freeze evaluator. Đổi definitions phải version và so candidates lại cùng policy.

Nộp: table/evidence tests/reports, comparisons và error taxonomy. Xong khi drop row/duplicate/failure bị lộ trong report; Lead/AI review.

### D4.1 — independent mock và optional public audit, tuần 5–9

Dependency và effort dự kiến: D2.2 + Lead protocol/public authority; 6–10h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Nhờ người không viết generator phác 2–3 independent layouts mỗi type; bạn render/label/QA, không clone train coordinates.
2. Giữ authors/source/family lineage và chấm slice riêng. Mock vẫn synthetic, không chứng minh real-document accuracy.
3. Public source tùy chọn: trước tải/sử dụng audit terms/license/PII/language/labels/access, theo quyền được giao.
4. Partial QA không biến thành full JSON/transcript; source trùng ảnh group cùng split; không nguồn phù hợp thì report loại và vẫn làm core synthetic.

Nộp: audited data card/manifests hoặc exclusion decision. Xong khi không có unknown PII/terms trong demo và independent layouts có gold đủ QA.

### D5.1 — frozen holdout và data handoff, tuần 10–12

Dependency và effort dự kiến: M6.1/O5.1/L4.1; 8–12h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Nhận candidate/evaluator manifests/hash từ Lead; không mở holdout trước protocol.
2. Chạy target 200–400 base documents tổng hai types, report per-type/family/quality/missing/table/independent slices, failures và support.
3. So B0/M0/M1 theo cùng protocol; uncertainty phù hợp sample size, không claim production từ synthetic.
4. Bàn giao data card/lineage/seed/config/manifest/evaluator/reports và commands đã chạy, người khác tái tạo subset được.
5. Nếu dùng final errors để tune, ghi rõ contamination/protocol mới, không tiếp tục gọi cùng test untouched.

Nộp: final report + reproducibility pack. Xong khi Lead/AI kiểm versions/counts/hash và dataset/model binaries không trong Git.

## Git Flow cho Data Engineer

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
