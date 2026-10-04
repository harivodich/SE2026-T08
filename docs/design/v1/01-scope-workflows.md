# 01 — Scope, yêu cầu và workflow

## 1. Bài toán và phạm vi

Tên: **Hệ thống trích xuất và kiểm duyệt dữ liệu chứng từ tiếng Việt từ ảnh/PDF**.

Người dùng mục tiêu là nhân viên nhập liệu chi phí/chứng từ. Hệ thống chuyển hình ảnh thành record có cấu trúc, giúp đối chiếu và sửa trước khi bàn giao JSON. Không xử lý thanh toán, không tự xác nhận tính hợp lệ pháp lý của hóa đơn.

| Mục | Scope bắt buộc |
|---|---|
| Ngôn ngữ | Tiếng Việt; model pretrained đa ngôn ngữ vẫn được dùng, nhưng dataset và nghiệm thu chỉ tiếng Việt |
| Loại | `receipt` và `invoice`, người dùng chọn lúc upload |
| Input | JPEG, PNG, PDF không mã hóa; một trang; văn bản in |
| Nội dung | Field đơn + bảng một trang, tối đa 30 dòng trong profile MVP |
| Output | Review record + business JSON đã được approve |
| Data | Synthetic/sample đã audit; không dùng thông tin khách hàng/bệnh nhân thật trong demo |
| Ngoài scope | Chữ viết tay, tài liệu bất kỳ, chatbot, phân loại tự động, phiếu giao hàng, OCR nhiều trang, integration ERP thật |

MVP profile: file tối đa 20 MiB, ảnh canonical tối đa 20 megapixel; PDF render dự kiến 200 DPI và giới hạn pixels. Worker deadline toàn job dự kiến 180 giây. Giá trị cấu hình phải benchmark trên hardware tuần 2, điều chỉnh trước tuần 3 và lưu ADR-0005. Không nhận tài liệu ngoài profile rồi cắt bớt nội dung âm thầm.

## 2. Yêu cầu và acceptance traceability

| ID | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| FR-01 | Upload đúng loại/file/profile | MIME + decoder kiểm thật, test corrupt/oversize/PDF nhiều trang |
| FR-02 | Xử lý nền có trạng thái | HTTP 202, status riêng, API vẫn phản hồi trong khi inference |
| FR-03 | OCR tiếng Việt giữ text và vị trí | Fixture dấu tiếng Việt, ảnh xoay, tọa độ đúng trên viewer |
| FR-04 | Extraction theo schema receipt/invoice | Result pass schema và báo metric field trên holdout |
| FR-05 | Bảng chi tiết giữ quan hệ dòng | Test mô tả xuống dòng, cột trống, tối đa 30 dòng |
| FR-06 | Thiếu/mơ hồ không bịa giá trị | `null`, issue và review flag trên missing/ambiguous fixtures |
| FR-07 | Review sửa field và dòng bảng | UI source bên trái, editor bên phải; save tạo revision |
| FR-08 | Không ghi đè sửa đồng thời | Hai tab sửa cùng version: một thành công, một HTTP 409 |
| FR-09 | Approval chỉ đúng snapshot | Approve revision cụ thể; kiểm blocking issues và warning ack |
| FR-10 | Export chỉ approved revision | Chưa approve: 409; payload/checksum đúng snapshot |
| FR-11 | Rerun giữ prediction và sửa cũ | New job/run; không thay head đang review/approved |
| FR-12 | Audit truy vết thay đổi | Actor, time, action, base/new revision, reason |
| FR-13 | Retry không nhân bản kết quả | Duplicate delivery chỉ một committed run/job |
| FR-14 | Có baseline và fine-tune tái lập | Manifest, seed, weights hash, evaluator, per-type metrics |
| NFR-01 | Bảo vệ truy cập | Operator chỉ tài liệu của mình; admin phạm vi đồ án |
| NFR-02 | Không lộ nội dung vào log | Log IDs/stage/error code; test redaction |
| NFR-03 | Giới hạn tài nguyên | Size/page/pixel/token/timeout; không retry OOM vô hạn |
| NFR-04 | Model rollback | Job pin pipeline manifest; đổi active release chỉ ảnh hưởng job mới |

## 3. Actors và quyền

- `operator`: upload; xem/run/review/approve/export tài liệu của chính mình. Một người được sửa và approve trong demo; không tuyên bố có kiểm soát bốn mắt.
- `admin`: quyền operator trong phạm vi toàn demo, xem lỗi, cập nhật active model release sau gate.
- Worker/dispatcher là system processes, không dùng credential người dùng.
- Data/AI engineers chạy training/evaluation offline; không có quyền tự đưa review corrections vào training.

Không thêm đăng ký public, password reset, MFA hay identity server. Account seed qua CLI, secret qua environment; không có mật khẩu mặc định trong repo. Login dùng bearer access token ngắn hạn, giữ trong memory frontend; refresh trang đăng nhập lại trong MVP, không triển khai refresh token flow.

## 4. Workflow A — Upload

1. Operator chọn `receipt`/`invoice`, upload file, gửi `Idempotency-Key`.
2. API xác thực và giới hạn streaming bytes trước decode; kiểm định dạng thực, malware-like malformed payload và profile. Không chỉ tin extension hoặc header MIME.
3. Tạo UUID và staging key. Tính SHA-256 khi stream; kiểm EXIF/PDF page count trong sandboxed resource limits. PDF mật khẩu/nhiều trang trả lỗi rõ.
4. Đưa file vào local private volume qua storage adapter. Object key do server sinh, không dùng tên upload làm path.
5. Transaction tạo `Document(UPLOADED)` + audit + idempotency receipt, rồi trả 201. File store và DB không có chung transaction: DB thất bại thì ghi orphan candidate cho cleanup theo manifest/staging TTL; không xóa bằng glob ngoài namespace.
6. Trùng key cùng request trả resource cũ; key khác nội dung trả 409. Trùng checksum cùng owner là cảnh báo/đường dẫn record cũ, không xóa tài liệu khác hoặc lộ tài liệu của user khác.

Upload chưa tự chạy model. UI có nút Xử lý; tạo được fixture từng bước, kiểm loại tài liệu trước inference.

## 5. Workflow B — Processing

1. POST job pin `document_type`, `schema_version`, `pipeline_manifest_id` và input checksum; transaction ghi job `QUEUED` + outbox + audit.
2. Dispatcher publish `job_id` sau commit, đánh dấu outbox delivered sau broker confirmation. Crash giữa publish/mark có thể phát lại; worker xử lý idempotent.
3. Worker claim job với lease + fencing token; nếu đã terminal thì ACK/no-op, nếu lease còn hiệu lực thì no-op và ACK delivery dư.
4. Đọc file; render canonical page, sửa EXIF orientation. Canonical viewer image có kích thước cố định và hash riêng.
5. Preprocess nhẹ: deskew/contrast khi bật config. Lưu transform invertible hoặc đánh dấu geometry unavailable. Không coi bbox trên ảnh preprocess là bbox viewer.
6. OCR → text/quad/score trên ảnh đã preprocess → map ngược tọa độ canonical → `OcrPage`.
7. Extraction adapter nhận canonical image, OCR context, document type và schema. Baseline rule adapter và model adapter dùng cùng contract.
8. Parse output bounded; schema validate; normalize; map evidence. Không dùng `eval`, không sửa giá trị bằng LLM vòng lặp không giới hạn.
9. Model output JSON không parse được: mặc định job FAILED `MODEL_OUTPUT_INVALID`; lưu raw output hạn chế truy cập để diagnose. Không bịa result placeholder. Chỉ thêm một repair attempt nếu spike chứng minh lợi ích và được đưa vào manifest/deadline.
10. Validation phân biệt structural errors và semantic warnings. Mơ hồ/không thấy field hợp lệ → `null` + issue, vẫn có thể tạo review draft.
11. Short transaction kiểm fencing token còn current, ghi `ExtractionRun` bất biến + job SUCCEEDED. Nếu document chưa có head, tạo draft revision đầu; nếu đã có head, result là candidate và không tự thay head.
12. ACK sau commit. UI polling theo job, hiển thị result hoặc lỗi actionable. Job SUCCEEDED nghĩa pipeline hoàn thành, **không nghĩa dữ liệu đúng/được approve**.

Mỗi attempt phải heartbeat giữa stages; inference dài dùng heartbeat timer riêng. Lease hết hạn không đủ để job cũ được commit: fencing token đã thay thì transaction bị từ chối.

## 6. Workflow C — Review/save/adopt

1. UI tải current revision, document version, source page và validation issues.
2. Highlight evidence khi có; không có vị trí thì hiển thị Không xác định được vùng nguồn.
3. Operator sửa value, thêm/sửa/xóa dòng bảng. Mỗi dòng có UUID runtime ổn định; reorder không làm mất identity.
4. PATCH gửi toàn corrected payload, `base_revision_id`, `expected_document_version`, reason. Full replacement payload đơn giản hơn JSON Patch cho MVP; server vẫn tính diff/audit.
5. Service kiểm owner, base=head, version; validate kiểu và normalize. Structural errors trả 422, không tạo revision.
6. Transaction append revision mới, update head bằng CAS, tăng document version, insert audit. Revision mới chưa approved; approval cũ vẫn gắn snapshot cũ.
7. Version stale trả 409 kèm current ID/version; UI giữ bản chỉnh local, tải server và cho người dùng reconcile. Không last-write-wins.
8. Adopt candidate từ rerun là một action riêng, cần cùng CAS; tạo revision mới từ candidate, không sửa revision cũ.

## 7. Workflow D — Approve/export

1. Approve yêu cầu head revision cụ thể + expected document version, review confirmation và issue IDs được acknowledge.
2. Tổng tiền là field required-for-approval trong cả hai schema. Số tiền mơ hồ/thiếu phải được sửa hoặc ghi nhận rejection; không có silent admin bypass.
3. Blocking structural/profile/rule errors không approve được. Warning về subtotal/tax arithmetic có thể acknowledge với reason; không ép công thức không đúng loại chứng từ.
4. Transaction append `Approval`, tăng document version, ghi audit. Payload revision bất biến; một revision chỉ một approval.
5. Export dùng `revision_id`, chỉ revision thuộc document/owner và có approval. Trả JSON envelope chứa schema version, document ID, revision ID và business payload; không trộn review metadata vào ERP payload.
6. Export repeat cùng revision/format/exporter-version cho cùng bytes/checksum. Sửa revision sau approval không làm artifact cũ thay đổi.
7. Nếu người dùng yêu cầu latest export trong khi có draft mới thì 409; có thể chọn rõ revision approved cũ. Không giả vờ draft mới đã approved.

## 8. Workflow E — Failure/retry/cancel

| Lỗi | Chính sách |
|---|---|
| File corrupt, PDF password/nhiều trang | Reject trước job hoặc FAILED terminal; user thay file |
| Storage/DB tạm unavailable | Retry tối đa 2 lần sau attempt đầu; backoff jitter; deadline bounded |
| OCR không đọc được | Null/issue nếu còn result hợp lệ; FAIL nếu engine/runtime không thực thi |
| OOM, model không load | FAIL terminal; admin giảm profile/check manifest, không autoretry cùng config |
| JSON model sai schema | FAIL; diagnose/fix model, không vòng LLM vô hạn |
| Worker crash | Lease expiry + dispatcher recovery; fencing ngăn late commit |
| Cancel | QUEUED → CANCELLED; RUNNING đặt cancel flag, worker kiểm trước commit; kill unsafe GPU không bắt buộc |

Automatic retry là attempt cùng job, cùng input và model version. Sau terminal failure, nút chạy lại tạo job mới; sửa file cần document mới. Một document tối đa một job nonterminal, enforced trong DB.

## 9. Review UI tối giản

Ba màn hình: danh sách chứng từ/job; upload; detail review. Detail gồm ảnh zoom/pan, field list, bảng items, issue panel, version/history, Save/Approve/Export. UI không tự quyết định approval policy hoặc tính toán confidence thay backend.

Operator xác nhận đã xem nội dung, kể cả field score cao. Confidence ưu tiên review, không thay con người approve. Dùng polling 2–5 giây có backoff khi tab hidden; không cần WebSocket trong scope này.
