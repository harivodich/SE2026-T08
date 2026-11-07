# Batch A — làm rõ R04, R07, R08 và R10

Ngày phân tích: **29/10/2026**. Snapshot gốc: `d608cc319e1184a6bcb097e0cffecfced91c8b42`.
Phần phân tích dưới đây mô tả snapshot trước sửa. Sau đó người dùng đã yêu cầu
implementation: R04/R07/R08/R10 được sửa local và kiểm RED→GREEN trong cùng ngày;
xem [plan và ledger](2026-10-29-four-fixes-plan.md) và [HISTORY](HISTORY.md).
Những fault-injection ghi là của reviewer vẫn là evidence báo cáo; các tests chạy
mới và limitations được ghi riêng trong HISTORY, không gộp hai nguồn thành một.

Nguồn yêu cầu: [compute protocol](../../../specs/contracts/compute-api.md),
[task M2.3](../ai-2-extraction.md), [workflow](../workflow.md).
Source: [compute endpoint](../../../src/vietdoc/entrypoints/api/app.py),
[response checker](../../../src/vietdoc/contracts/compute.py).

| Mã | Bản chất lỗi | Kết quả cần hướng tới |
|---|---|---|
| R04 | Đồng hồ bắt đầu muộn và dừng kiểm quá sớm | Một budget cho toàn bộ xử lý kể từ ingress, không success sau hết hạn |
| R07 | Lỗi hạ tầng bị coi thành lỗi chứng từ | Trả đúng input error hoặc service error để Java có retry policy phù hợp |
| R08 | Byte cap chưa giới hạn JSON nesting | Metadata quá sâu bị từ chối bằng typed error, không thoát RecursionError |
| R10 | Có ít nhất hai artifacts chưa chắc có OCR | Bắt buộc đúng loại canonical và OCR tại semantic response boundary |

## R04 — Deadline accounting: tính thiếu thời gian

### Hiện tại và nguyên nhân

Trong `app.py`, endpoint bắt đầu ở dòng 206 nhưng deadline được tạo ở dòng 257,
sau parse multipart, decode metadata, đọc file, hash, release/readiness checks và
tạo attempt directory. Service đã dùng thời gian nhưng chưa trừ vào budget.

Sau `pipeline.run()`, dòng 272 kiểm deadline. Tiếp theo service validate response,
log success và serialize JSON; chưa kiểm thời gian đã tiêu thêm ở các bước này.

Ví dụ minh họa: Java gửi budget 100 ms. Python đọc request mất 250 ms, rồi mới bắt
đầu một cửa sổ 100 ms khác. Pipeline chạy 20 ms vẫn có thể được nhận success dù
thời gian đã dùng khoảng 270 ms. Reviewer báo đã tái hiện kiểu lỗi accounting này;
các con số không phải benchmark latency của model.

### Hậu quả

Java có thể đã timeout/cancel trong khi Python tiếp tục làm việc hoặc báo success.
Điều này tăng stale work và làm budget hai runtime không còn cùng ý nghĩa. Không
có bằng chứng từ riêng finding này rằng Java đã commit sai: fence/deadline ở Java
vẫn phải kiểm độc lập.

### Hướng sửa đề xuất

1. Ghi `arrival` bằng monotonic clock ở ingress trước đọc body, giữ timestamp đó
   trong request context; không dùng một deadline global dùng chung các request.
2. Sau khi metadata hợp lệ, tính `deadline = arrival + remaining_budget_ms / 1000`.
   Không reset khi đổi stage hoặc bắt đầu worker.
3. Kiểm trước dispatch và ở đầu worker để thời gian chờ threadpool cũng tiêu cùng
   budget. Hết hạn thì không gọi pipeline.
4. Kiểm sau pipeline, sau validate và sau serialize, trước quyết định success.
   Output preparation và R09 phải dùng cùng deadline.
5. Trả `504 COMPUTE_TIMEOUT` đúng envelope khi không còn budget; giữ slot đến khi
   compute thực sự kết thúc theo cơ chế ownership của R05.

Metadata có thể chưa tới khi upload treo. Vì vậy ingress timeout cần chính sách
riêng, không chờ đọc được `remaining_budget_ms` mới giới hạn slow body. Chỉ sửa
accounting không tự tạo hard-stop cho native/GPU call hoặc bảo đảm client nhận hết
response trước deadline; các khả năng đó cần verification riêng.

### Regression cases cần có

| Case | Assertion chính |
|---|---|
| Upload đã dùng hết budget | 504, pipeline call count = 0 |
| Budget hết khi chờ worker | Worker không gọi pipeline, slot được xử lý đúng ownership |
| Pipeline kết thúc quá hạn | Không trả 200; typed timeout |
| Validator/serializer làm hết budget | Không success log hoặc 200 sau hết hạn |
| Request đủ budget | Response hợp lệ vẫn 200; deadline không bị reset qua stage |

Ưu tiên clock có thể điều khiển và synchronization events cho test ổn định; không
dùng timing sát ngưỡng như cách duy nhất chứng minh behavior.

## R07 — Storage errors: đổ lỗi nhầm cho input

### Hiện tại và nguyên nhân

`app.py` dòng 210 gọi `request.form()`. Nhánh `except Exception` dòng 213 gom mọi lỗi
ở bước này thành `422 INPUT_INVALID`, `retryable=false`. Nhưng multipart parsing
có thể spool upload ra temporary storage; lỗi disk-full hoặc permission không có
nghĩa bytes chứng từ sai. Reviewer fault-inject ENOSPC và nhận đúng nhánh báo nhầm
này; reviewer không làm đầy disk thật.

`upload.read()` dòng 228 và `form.close()` dòng 230 cũng là các điểm có thể lỗi I/O,
nhưng hiện chưa có classification nhất quán tại endpoint. Exception trong cleanup
còn có thể che outcome đã xác định trước đó.

### Hậu quả và hướng phân loại

Java có thể terminal-fail một chứng từ hợp lệ vì nhận lỗi permanent của input,
trong khi service mới là bên thiếu tài nguyên.

| Tình huống | Outcome đề xuất |
|---|---|
| Multipart sai cấu trúc/thiếu part/metadata sai | 422 INPUT_INVALID, không retry |
| Request/file vượt byte cap | 413 INPUT_TOO_LARGE, không retry |
| Storage unavailable khi parse/read/cleanup | Typed service failure; đề xuất tái dùng 503 AI_NOT_READY như nhánh mkdir hiện tại |
| Programming exception bất ngờ | INTERNAL_ERROR qua boundary kiểm soát; không tự chuyển thành lỗi retryable |

Mapping storage/retry ở trên cần Backend review theo allowlist hiện có. Không thêm
error code vào shared schema riêng một phía. Retryable không có nghĩa Java retry
vô hạn: vẫn có attempt/deadline budget, và permission/config lỗi cần vận hành xử lý.

Hướng sửa bao phủ cả parse/read/close, bắt expected exceptions đủ hẹp và giữ thông
báo không chứa raw document, temporary path hoặc exception text. Cleanup phải best
effort và có outcome ưu tiên rõ, không bị exception thứ hai che lỗi gốc. File handle
và compute permit phải có owner rõ; không dùng outer release vô điều kiện làm hỏng R05.

### Regression cases cần có

- Fault-inject disk-full/permission khi parse và lỗi I/O khi upload read/close.
- Malformed và streamed oversize vẫn giữ đúng input error, không bị đổi thành 503.
- Pipeline không chạy khi chuẩn bị input chưa thành công.
- Không để lộ path/payload; request kế tiếp vẫn dùng được slot khi lỗi đã kết thúc.
- Kiểm cleanup thật sự được gọi; test lỗi cleanup không tạo untyped exception hoặc
  double-release. Không chỉ assert status code.

## R08 — Metadata sâu: byte limit không phải depth limit

### Hiện tại và ví dụ

`MAX_METADATA_BYTES = 16 * 1024` giới hạn part metadata. Tuy nhiên dòng 220 gọi
`json.loads(metadata)` trước schema validation và chỉ bắt `ValueError`. Với JSON
lồng sâu, decoder có thể ném `RecursionError`, không đi qua nhánh typed input error.

Ví dụ một object có field `x` chứa 5.000 nested arrays chỉ khoảng 10 KiB. Nó dưới
byte cap nhưng vẫn có thể vượt recursion limit. `x` là key ngoài schema, nhưng schema
không giúp được vì decoder phải hoàn thành trước mới có Python object để validate.
Reviewer ghi đã tái hiện case này; JSON nông với key sai vẫn bị 422 như bình thường.

### Hướng sửa đề xuất

1. Chọn depth cap rõ ràng ở request boundary; metadata hiện tại chỉ cần flat object.
   Đây là cap cần ghi nhận và review, không tự coi một con số đề xuất là contract đã duyệt.
2. Scan nesting trước decode, hiểu strings và escape sequences. Dấu `[` trong
   một JSON string không được tính như array nesting.
3. Bắt expected malformed/decoder-limit errors và trả `422 INPUT_INVALID`, không
   phản hồi stack trace. Byte cap vẫn giữ nguyên.
4. Đề xuất reject duplicate keys thay vì để decoder âm thầm giữ giá trị cuối.
   Đây là policy wire cần chốt với Backend để Java/Python hiểu cùng metadata.
5. Nếu metadata chưa parse tin cậy thì `attempt_id` trong error có thể null theo
   schema; không dùng text bị lỗi để tạo artifact path.

Không tăng recursion limit của toàn process để nhận input này, vì chỉ đẩy ngưỡng
lỗi ra xa và không tạo resource bound. Không tái dùng mù depth cap của model output:
metadata và extraction payload là hai loại JSON có nhu cầu nesting khác nhau.

### Regression cases cần có

| Case | Assertion chính |
|---|---|
| Metadata hợp lệ | Giữ happy path |
| Ngay dưới/trên depth cap | Outcome ổn định; trường hợp sai business schema vẫn 422 |
| Brackets/escaped quotes trong string | Scanner không đếm nesting giả |
| JSON thiếu dấu đóng hoặc quá sâu | Typed INPUT_INVALID, không RecursionError ra ngoài |
| Duplicate job/run/attempt key | Theo policy đã chốt, không last-key-wins âm thầm |
| Request hợp lệ sau request bị reject | Service vẫn hoạt động; không rò file/permit |

## R10 — Thiếu OCR artifact nhưng response vẫn được nhận

### Hiện tại và nguyên nhân

[compute-response schema](../../../specs/contracts/compute-response.schema.json)
quy định artifacts có ít nhất hai entries và `kind` nằm trong enum. Hai entries
có thể là `canonical_page` và `raw_prediction`; số lượng không chứng minh có OCR.

`ComputeContracts.check_response()` dòng 107–142 kiểm schema, correlation, duplicate
keys, prefix và đúng một canonical artifact khớp canonical metadata. Chưa có điều
kiện bắt buộc `kind == "ocr"`, trong khi protocol yêu cầu canonical page/OCR artifacts.

Ví dụ lấy [fictional fixture](../../../tests/contract/compute-response.json), giữ
nguyên artifact canonical rồi đổi kind entry OCR thành `raw_prediction`: cấu trúc
còn đúng schema và các semantic checks hiện tại không kiểm loại artifact đã mất.
Reviewer ghi checker vẫn nhận. Đây không phải bằng chứng OCR bytes đã được sinh.

### Hậu quả và hướng sửa đề xuất

Consumer có thể nhận success envelope thiếu output OCR bắt buộc, nên không đủ dữ
liệu cho việc đối chiếu/evidence theo protocol. Việc `payload` đã có field values
không thay thế OCR output cần bàn giao.

- Enforce có OCR artifact trong producer semantic check, ngoài canonical check đã có.
- Giữ schema/correlation/prefix/duplicate asset key/hash correlation checks hiện tại.
- Không tự đặt rule exactly-one OCR hoặc kind/media restrictions mới nếu protocol
  chưa chốt; mọi ràng buộc bổ sung phải thống nhất với AI-1/Backend.
- Khi nối pipeline thật, writer phải tạo file OCR và canonical bytes thật. Không
  thêm declaration/hash giả chỉ để response vượt checker.

Giới hạn trách nhiệm: producer metadata checker không chứng minh file tồn tại hay
hash/size đúng bytes. Writer/decoder phải kiểm actual artifacts và image profile;
Java vẫn stream-copy/hash/size/decode bản copy rồi promote sang committed storage.
Không serve trực tiếp mutable attempt files.

### Regression cases cần có

| Case | Assertion chính |
|---|---|
| Canonical + raw_prediction, thiếu OCR | ContractError; endpoint trả 422 OUTPUT_INVALID |
| Canonical + OCR hợp lệ | Tiếp tục pass |
| Chỉ OCR, thiếu canonical hoặc canonical hash lệch | Reject; không làm yếu kiểm hiện có |
| Asset key trùng/sai attempt prefix | Reject như trước |
| Artifact declaration hợp lệ nhưng file chưa có | Metadata test không được báo thành actual-provider acceptance |

## Quan hệ với các finding còn lại

R04 liên quan R05 (slot/cancel) và R09 (validate/serialize trước success). R07 phải
giữ cleanup/ownership của R05. R08 và R10 cần regression tests đi vào CI qua R17.
Sửa riêng bốn mục này chưa đủ đóng toàn Batch A: R05/R09/R14/R17 vẫn phải được kiểm.

AI-2 sở hữu producer code; Backend review budget/error/wire compatibility; AI-1
review OCR artifacts; Lead quyết acceptance. Tài liệu này không đổi trạng thái
review hoặc cấp quyền push/merge. Implementation sau phân tích được làm theo yêu
cầu riêng của người dùng và chưa có peer/Lead acceptance.
