<!-- Metrics measured on the frozen offline snapshot; artifact-relative paths below refer to the shared handoff ZIP, not repository files. -->
# Nghiệm thu dev model — 26/11/2026

**Kết luận: đã chạy xong B0/M0/M1 thật trên `nvit-train`, nhưng chưa đủ điều kiện nghiệm thu model V1 hoặc bật serving.** Fine-tune một epoch D22 đã chạy được; chất lượng và độ đúng định dạng chưa đạt. Không cần yêu cầu AI2 làm lại G0/install/token/OCR join; cần xử lý các lỗi đo được dưới đây.

## 1. Kết quả thực tế

Ba phương pháp dùng cùng 16 mẫu dev native OCR: 8 receipt, 8 invoice, gồm clean/mild/crop/unreadable. Đây là **4 base documents, mỗi base có 4 variants**, không phải 16 chứng từ độc lập. Không bỏ mẫu failure; 48 scalar present được chấm, 48 scalar obscured bị loại đúng policy. Final assets không được đưa lên host và không được dùng để tune/chấm.

| Chỉ tiêu | B0: OCR + rules | M0: Qwen pretrained | M1: Qwen + adapter một epoch |
|---|---:|---:|---:|
| Raw JSON hợp lệ | 16/16 | 13/16 | 8/16 |
| Raw business schema hợp lệ | 16/16 | **0/16** | **0/16** |
| Schema hợp lệ sau parser/normalizer dùng chung | 16/16 | 6/16 | 4/16 |
| Present scalar normalized EM | 16/48 = 33,33% | 15/48 = 31,25% | 17/48 = 35,42% |
| Receipt present scalar EM | 4/18 = 22,22% | 8/18 = 44,44% | 10/18 = 55,56% |
| Invoice present scalar EM | 12/30 = 40,00% | 7/30 = 23,33% | 7/30 = 23,33% |
| Total amount EM | 0/8 | 3/8 | 3/8 |
| Receipt total EM | 0/4 | 2/4 | 2/4 |
| Invoice total EM | 0/4 | 1/4 | 1/4 |
| Table end-to-end cell accuracy | 0/112 | 37/112 = 33,04% | 13/112 = 11,61% |
| Matched-row cell accuracy | null: chưa match ô nào | 37/51 = 72,55% | 13/23 = 56,52% |
| Exact fully-labelled row | 0/16 | 0/16 | 0/16 |
| Mẫu failure sau normalization | 0/16 | 10/16 | 12/16 |
| p95 từng mẫu, nearest-rank | 34 ms | 7.950 ms | 27.449 ms |

**Điểm quan trọng:** bảng normalized là benchmark chẩn đoán sau cùng một normalizer, không phải kết quả được phép đi vào serving. Replay raw generations qua `QwenInference.run` hiện hành xác nhận **M0 và M1 đều được nhận 0/16 mẫu** vì contract yêu cầu raw schema hợp lệ. Không được quảng bá 35,42% là quality của candidate đã usable trong ứng dụng; không hạ raw-schema gate để làm candidate đạt.

So M1 với M0: scalar tăng 2/48 trường, total không tăng, schema ổn sau normalization giảm từ 6 xuống 4 mẫu, table cells đúng giảm từ 37 xuống 13, p95 tăng do một lần generation bị cắt ở giới hạn 1.280 output tokens. Kết quả này **không đủ để chọn M1 thay M0**. B0 cũng không đủ chất lượng extraction đầy đủ: nó abstain nhiều, thiếu cả 8 total và không trả dòng hàng trên dev này. Giữ B0 làm đường đi an toàn hiện tại không có nghĩa B0 đã đạt V1 quality.

`comparison.fair=true`, không thiếu candidate hoặc mismatched pins. Chỉ tiêu target trong workflow vẫn là proposed; ngay khi dùng chúng làm mốc tham khảo, kết quả hiện tại cũng còn cách xa. Không dùng việc “target chưa chốt” làm lý do duy nhất: đã có lỗi output/schema/semantic cụ thể chặn nghiệm thu.

## 2. Lỗi cần AI2 sửa, theo ưu tiên

### P1 — Output không đạt contract raw

- M0 có 7 `OUTPUT_SCHEMA_INVALID`, 1 `OUTPUT_MALFORMED_JSON`, 2 `OCR_UNREADABLE`; 6 mẫu normalized hợp lệ vẫn không đạt raw schema.
- M1 có 4 `OUTPUT_SCHEMA_INVALID`, 5 `OUTPUT_MALFORMED_JSON`, 1 `OUTPUT_TRUNCATED`, 2 `OCR_UNREADABLE`; 4 mẫu normalized hợp lệ vẫn không đạt raw schema.
- Ví dụ M1 `v0-1-d22-smoke-receipt-f07-b0000-clean`: output lặp key `unit_price` trong từng item; strict parser đã từ chối. Không sửa bằng `json.loads` chọn key cuối.
- Ví dụ M1 `...receipt-f06-b0000-clean`: `transaction_date="29/04/2026"`, `quantity="895.000đ"`, `unit="đ"`, `unit_price="2.685.000 đ"`. Output không theo schema/canonical format, đồng thời nhầm vai trò dữ liệu.

**Làm tiếp:** kiểm decoded train target/mask và prompt inference, bổ sung regression các key bắt buộc/duplicate/canonical date/decimal strings; chạy tiny-train sanity có generation check, rồi chọn một hypothesis cho bounded run #2. Nếu dùng constrained decoding phải có implementation/version/hash, tests invalid/timeout và chấm lại đủ population. Không auto-repair/gỡ required raw schema rồi gọi lỗi đã sửa.

### P1 — Dòng hàng sai và mất hàng, fine-tune chưa cải thiện

- M1 match 5/32 annotation rows, thiếu 27; có 1 extra row. M0 match 11, thiếu 21 và có 14 extra. Có 16 rows đầy đủ nhãn, 16 rows partial; metric cell chỉ tính 112 present cells và loại 48 obscured cells.
- M0 `...receipt-f07-b0000-clean`: text header `Mặt hàng / dịch vụ` bị đưa thành description của một item.
- M1 `...receipt-f06-b0000-clean`: giá bán `895.000đ` thành quantity; `...mild` sinh quantity `2` và line total `1790000`, trong khi tổng/document mapping chưa được chứng minh đúng.
- Không có exact fully-labelled row đúng ở cả M0/M1. Chỉ báo matched-cell accuracy sẽ che số hàng mất, nên luôn kèm end-to-end cells/unmatched/extra/duplicate.

**Làm tiếp:** tách lỗi header/column mapping, duplicate description, giá và quantity, total/tender; thêm case cột đảo thứ tự, receipt không có item, item nhiều dòng, unit absent, amount lặp. Mỗi sửa có test độc lập; không hard-code ID hay output của D22.

### P1 — Tự điền dữ liệu không có trong OCR

- OCR `...receipt-f06-b0000-crop` chỉ có header bảng, item, giá/đơn vị/cộng dòng; không có ngày/giờ. M1 vẫn sinh `2023-10-10` và `12:00`.
- OCR `...receipt-f06-b0000-unreadable` chỉ có `_—Ế.`. M1 sinh tên cửa hàng, địa chỉ, ngày/giờ và nhiều item; M0 cũng sinh thông tin cửa hàng/địa chỉ/ngày giả.
- Các output sai schema đang bị chặn nên chưa thành kết quả business hợp lệ; đây vẫn là failure cần đưa vào phân tích raw output. Chỉ nhìn `false_fill` trên prediction đã qua gate sẽ bỏ sót nhóm này.
- Trong các output normalized đã chấm, M1 có 1 scalar và 2 cells được fill ở trạng thái obscured. Đây là accounting riêng với false fill ở field absent.

**Làm tiếp:** giữ policy partial OCR, bind evidence theo observed text/canonical geometry; absent/obscured/unlabeled tách riêng. Thiếu evidence thì null/unavailable/ambiguity, confidence null nếu chưa calibration. Không đổi gold hoặc tự fill ngày/giờ. Trường bắt buộc thiếu vẫn chặn approve.

### P2 — Budget và lựa chọn candidate cần đo lại có mục tiêu

M1 `...receipt-f07-b0000-mild` đạt giới hạn 1.280 output tokens và bị `OUTPUT_TRUNCATED`, mất 27,449 giây. Không tăng budget vô điều kiện: xem raw generation, duplicate/repetition, EOS và schema-learning trước; thay budget phải preflight lại cả population và peak memory. M1 hiện chưa có lý do đo được để promote.

## 3. Phần đã nghiệm thu được

- Torch/Transformers/PEFT CUDA thực hoạt động; không còn blocker cài torch/GPU, tokenizer/context hay OCR join của lượt D22.
- **363/363 ML tests Linux đạt, không skip**, gồm guard chống đọc nhầm final, failure accounting và reprovision lineage. 21 focused tests local và Ruff đạt; patch 14 file áp dụng sạch trên develop SHA `594336013dbc122326169a7c7e6df09e1d9d22c6`.
- M0/M1 load lần lượt, không đồng thời giữ hai base model. M0 load khoảng 6,85 giây, M1 khoảng 6,18 giây. GPU allocated peak: M0 3.798.547.456 bytes, M1 3.835.842.560 bytes; reserved peak lần lượt 3.904.897.024 và 4.011.851.776 bytes. Đây là offline dev inference, không phải HTTP/concurrency capacity benchmark.
- Cả inference và scoring exit 0; exit 0 nghĩa là đã thống kê/chấm đủ mẫu, không đồng nghĩa quality đạt.
- Run/checkpoint/config/schema/model/tokenizer/engine/profile/evaluator pins được kiểm. Snapshot base tái tải từ cùng immutable revision và từng required file được kiểm với metadata official; proof giữ rõ envelope manifest cũ/mới, không sửa run manifest train.
- Source chưa commit/push/merge, model chưa được activate, chưa chạy final holdout, chưa claim actual Java/PostgreSQL/HTTP E2E của model này.

## 4. Bằng chứng và cách gửi AI2

- `host-evidence/evaluation/dev-score-v1/comparison.json`: báo cáo versioned đầy đủ B0/M0/M1.
- `host-evidence/evaluation/summary.json`: metrics, latency và memory tóm tắt.
- `host-evidence/evaluation/scalar-errors.csv`: lỗi từng scalar theo candidate/sample/field.
- `host-evidence/evaluation/dev-inference-v1/{M0,M1}/samples.json`: raw outputs, token count, parse status, lỗi và thời gian từng mẫu.
- `host-evidence/evaluation/serving-contract-replay.json`: replay output đã ghi qua consumer thật, 0/16 accepted mỗi model; không phải một lượt HTTP/GPU mới.
- `host-evidence/ml-tests-final.xml`, `controller.log`: tests và log inference thật trên host.
- `../ai2-v1-completion-2026-11-26.md`: thứ tự sửa, các increment đến V1, tests/acceptance, dependency packets và commit groups.
- `README-chay-lai.md`, `AI2-training-evaluation.patch` trong packet: cách tiếp nhận và chạy lại; không cần chờ Lead tạo PR hỗ trợ riêng.

Archive evidence tải từ host: `acceptance-evidence.tar.gz`, SHA-256 `67e55e656f5d023d2a7e09b625b4acb6da6f0e181ce39faf9b19b6f7248a18a3`. Đã đối chiếu hash và giải nén an toàn ở local trước cleanup host. Summary/CSV/replay bổ sung ở local được đóng vào packet riêng, không sửa archive evidence gốc.

Đã dọn duy nhất `/home/hainh/vietdoc-v1-eval-20261125` sau khi kiểm archive/source local khớp host; trả lại **20.019.503.104 bytes** dung lượng cấp phát. Không xóa cache dùng chung hoặc thư mục dự án khác. GPU cuối lượt còn 15 MiB, không còn inference của lượt này. Lần chạy lại cần khôi phục môi trường/model theo README; không còn service/model nào chạy ngầm trên host từ lượt nghiệm thu này.

## 5. Dependency còn lại

AI2 có thể làm ngay toàn bộ P1/P2, decoded-target checks, error analysis, serving adapter/lifecycle, negative tests và release/rollback tooling trên D22 hiện có; **không cần chờ Data/AI1 để bắt đầu**. Dataset pilot lớn hơn và OCR tương ứng vẫn là input cần cho quality/generalization cuối, còn candidate freeze/final report và actual E2E là điều kiện nghiệm thu cuối. Không thể gọi các điều kiện này “đã xong hết” chỉ từ lượt chạy D22.

Trong lượt tiếp tục này không gọi thêm Astra/Claude/Gemini. Đã dùng review Astra có sẵn và controller tự sửa/kiểm chứng; không phát sinh lượt model-review phụ.

## Bổ sung khi chuẩn bị push — 26/11/2026

Source bàn giao mới được ghép từ develop `5943360`, không phải chép đè checkout thí nghiệm cũ. Kiểm tích hợp phát hiện thiếu seam `max_manifest_samples`; đã thêm đúng tham số/CLI bounded (default20, opt-in tới200) vào file OCR hiện hành, giữ code geometry/timing đã merge. Suite seam/handoff đạt 132 tests và 97 subtests; evaluator + CI gate tests đạt 62 tests/68 subtests, wheel smoke bị đường dẫn sandbox Windows làm lỗi đã chạy lại build sạch ngoài sandbox đạt 1/1. Không sửa/xóa tests để làm xanh.

Regression loss/gradient dùng torch thật nên required AI CI được bổ sung torch CPU `2.14.1+cpu`; không chạy GPU, tải model hay training trong CI. Actionlint và zizmor chạy trên Linux đạt (các suppressions có sẵn giữ nguyên); validator Windows bị Application Control chặn. Ruff tập trung evaluator/scripts đạt; chưa làm cleanup các cảnh báo style kế thừa ở toàn bộ training module.

Theo yêu cầu mới đã gọi một lượt Astra medium ngắn để kiểm dependency. Hai điểm được bổ sung: không gửi token profile Data 24/11 như current; AI2 phải trả sớm ACK reader/partial và interface/error fixtures cho consumer. Không coi lượt phân tích này là review source độc lập của branch mới. Xem [dependency hiện hành](../cross-role-unblock-2026-11-26.md) và [nội dung gửi AI2](../ai2-handoff-message-2026-11-26.md).
