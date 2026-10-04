# 03 — Schemas, API và module contracts

## 1. Quy ước chung

IDs runtime UUID; `document_type` = `receipt|invoice`; schema = `receipt.v1|invoice.v1`; `language=vi`. Backend timestamps UTC ISO 8601; transaction time trên chứng từ giữ local time, không tự gán timezone nếu ảnh không có.

Business values là string/null; tiền và quantity dùng decimal string sau normalize (`1250000`, `1.5`), không binary float. Date = YYYY-MM-DD, time = HH:MM hoặc HH:MM:SS; type-specific semantic validators kiểm ngày/giờ thực, vì regex không đủ.

Mọi field key luôn có mặt trong prediction để client ổn định; value null biểu diễn không xác định. `items=[]` nghĩa không phát hiện dòng đủ tin cậy, không bảo đảm tài liệu không có bảng. Evidence/issue phải cho biết coverage. Missing training label có `label_status=unlabeled`, khác nhãn gold `absent`.

## 2. Receipt v1

| Field | Meaning | Approval policy |
|---|---|---|
| merchant_name | Tên cửa hàng/người bán | Nullable; warning khi thiếu |
| merchant_address | Địa chỉ bên bán trên chứng từ | Nullable |
| transaction_date | Ngày giao dịch | Nullable; warning khi thiếu/ambiguous |
| transaction_time | Giờ giao dịch | Nullable; không suy đoán |
| total_amount | Tổng phải thanh toán/giao dịch | Required non-null để approve |
| items | Dòng hàng đọc được | Không ép có hàng nếu ảnh không có bảng; user xác nhận completeness |

Receipt number/payment method chưa bắt buộc trong v1. Thêm sau phải update schema và evaluation coverage, không trả key tùy hứng.

## 3. Invoice v1

| Field | Meaning | Approval policy |
|---|---|---|
| invoice_number | Số chứng từ ghi trên ảnh | Nullable; warning thiếu |
| issue_date | Ngày lập | Nullable; không dùng ngày đến hạn thay thế |
| seller_name | Bên bán/cung cấp dịch vụ | Nullable; warning thiếu |
| buyer_name | Bên mua | Nullable; không lấy người ký thay |
| subtotal | Giá trị trước các khoản điều chỉnh khi được ghi | Nullable |
| tax_amount | Tiền thuế ghi rõ | Nullable; không suy ra từ tax rate |
| discount_amount | Số tiền giảm giá ghi rõ | Nullable |
| total_amount | Tổng ghi trên chứng từ | Required non-null để approve |
| items | Dòng sản phẩm/dịch vụ | Cùng LineItem schema |

Không kiểm nhận diện hóa đơn hợp lệ pháp lý, MST, QR xác thực hoặc ký số trong v1. `currency` không đưa vào business v1 vì scope target VND; nếu tài liệu không phải VND/không rõ monetary convention thì warning hoặc unsupported profile, không suy ra dựa language alone.

## 4. Line item và provenance

Business line item gồm `description`, `quantity`, `unit`, `unit_price`, `line_total` (string/null). Runtime editor gán `row_id` UUID ngoài business payload, map 1:1 với items và giữ qua reorder. Output model dùng index tạm; backend tạo identity, không yêu cầu model sinh UUID.

Field metadata dùng JSON Pointer (`/total_amount`, `/items/0/line_total`) và map stable row ID trong revision metadata. `raw_value`, `value_origin=prediction|human|absent`, `source_regions[]`, `ocr_score`, `confidence`, `confidence_method`, `review_flags[]`.

Source region = canonical page index 0, normalized quad 4 điểm [x,y] trong [0,1], OCR block IDs. Viewer width/height thuộc PageAsset, không lấy dimension ảnh preprocess. Evidence do matching/alignment thực, model bbox chưa verify không coi là ground truth.

Confidence null nếu chưa calibrated. OCR score độc lập; không copy thành field probability. Human correction giữ original evidence provenance và đánh dấu manual value, không gán confidence=1.0.

## 5. Contracts tính toán

Các chữ ký dưới là thiết kế, không phải API thư viện được xác minh.

```python
class OcrPort(Protocol):
    def recognize(self, page: PreparedPage, limits: PipelineLimits) -> OcrPage: ...

class ExtractorPort(Protocol):
    def extract(self, request: ExtractionInput) -> RawPrediction: ...

class StoragePort(Protocol):
    def open_read(self, key: str) -> BinaryIO: ...
    def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredAsset: ...

class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

`ExtractionInput`: document type/schema, image asset, ordered OCR blocks, limits, model manifest; OCR text encoded như untrusted data, không nối vào system instructions. `RawPrediction` có raw output, finish reason, timing; `PipelineResult` mới là validated payload/evidence/issues/provenance.

`PreparedPage`: canonical image key/dimensions, processed image key, inverse transform, geometry status. `OcrPage`: ordered blocks với immutable block_id/text/quad/score, OCR version. Không return ndarray qua broker; computation dùng object nội bộ, broker chỉ ID.

## 6. REST API v1

| Method/path | Request chính | Success | Constraints |
|---|---|---|---|
| POST /api/v1/auth/token | Credentials theo auth library | 200 token | Seed account; rate limit; không log password |
| POST /api/v1/documents | multipart file + document_type; Idempotency-Key | 201 document | Size/type/profile; owner |
| GET /api/v1/documents | cursor, status/type filter | 200 page | Owner scope, default 20 max 100 |
| GET /api/v1/documents/{id} | — | 200 metadata/version/head | Authorization |
| POST /api/v1/documents/{id}/jobs | profile/release option allowed; Idempotency-Key | 202 job | One active job; pin manifest |
| GET /api/v1/jobs/{id} | — | 200 state/stage/error | Authorization qua document |
| POST /api/v1/jobs/{id}/cancel | expected state | 202 request hoặc 200 cancelled | Terminal không mutate |
| GET /api/v1/documents/{id}/runs | cursor | 200 history | Prediction immutable |
| GET /api/v1/runs/{id} | — | 200 result | Không expose raw model output mặc định |
| GET /api/v1/documents/{id}/pages/0 | — | 200 image | Canonical page qua authorized stream |
| GET /api/v1/documents/{id}/revisions | cursor | 200 revisions | Owner scope |
| GET /api/v1/revisions/{id} | — | 200 snapshot/issues | Relation guard |
| PATCH /api/v1/documents/{id}/review | base_revision_id, expected_document_version, payload, reason | 201 new revision | CAS + validation |
| POST /api/v1/documents/{id}/adopt-run | run_id, base_revision_id, expected_document_version, reason | 201 revision | Explicit candidate adoption |
| POST /api/v1/documents/{id}/approve | revision_id, expected_document_version, confirmed_review, acknowledged_issue_ids, reason | 201 approval | Current head; blocking issue check |
| POST /api/v1/documents/{id}/exports | revision_id, format=json | 201 artifact hoặc 200 existing | Approved snapshot |
| GET /api/v1/exports/{id}/download | — | 200 attachment | Owner; schema/revision IDs |
| GET /api/v1/documents/{id}/audit | cursor | 200 events | Minimal details |
| POST /api/v1/admin/model-releases/{id}/activate | release manifest đã có trên disk | 200 active release | Admin; release gate evidence |
| GET /health/live, /health/ready | — | 200/503 | Không disclose secrets |

Không nhận arbitrary model path, object key, URL hoặc prompt trong public API. ID mapping resolver do server sở hữu. Run mới từ terminal failure dùng POST jobs; retry nội bộ không là endpoint riêng.

## 7. Ví dụ save review

```json
{
  "base_revision_id": "22222222-2222-4222-8222-222222222222",
  "expected_document_version": 3,
  "reason": "Sửa tổng tiền sau khi đối chiếu ảnh mẫu",
  "payload": {
    "merchant_name": "CỬA HÀNG MẪU",
    "merchant_address": null,
    "transaction_date": "2026-10-04",
    "transaction_time": null,
    "total_amount": "125000",
    "items": []
  }
}
```

Response 201 trả new revision ID, parent ID, document version=4, issues và review state DRAFT. Ví dụ là dữ liệu giả lập, không phải prediction hoặc metric thật.

## 8. Error envelope

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "Tài liệu đã có phiên bản mới. Hãy đối chiếu lại trước khi lưu.",
    "request_id": "demo-request-id",
    "details": {"current_document_version": 4}
  }
}
```

400 malformed request; 401 invalid/expired token; 403 role action không allowed; 404 document inaccessible hoặc không tồn tại; 409 version/active job/idempotency/export precondition conflict; 413 byte limit; 415 unsupported media; 422 payload/schema/profile invalid; 429 admission/rate limit; 503 dependency unavailable. Không expose exception traceback/path/token/raw payload.

Job failure dùng enum `INPUT_CORRUPT`, `PROFILE_UNSUPPORTED`, `OCR_RUNTIME_ERROR`, `MODEL_LOAD_FAILED`, `MODEL_OUTPUT_INVALID`, `RESOURCE_EXHAUSTED`, `DEADLINE_EXCEEDED`, `STORAGE_UNAVAILABLE`, `INTERNAL_ERROR`. User thấy reason/action; traceback chỉ restricted diagnostic.

## 9. Validation policy

Structural: key/type/array limit, finite bbox, pointer tồn tại, enum/type/schema compatibility. Date/time semantic: ngày thực, không tự biến invalid thành date gần đúng. Money: decimal parse theo source convention, giữ raw string, không xóa mọi dấu phẩy/chấm tùy tiện.

Arithmetic chỉ áp dụng khi known rule và đủ operands: qty×unit_price≈line_total, subtotal+tax−discount≈total. Tolerance theo rounding policy được manifest hóa; service charge/thuế gộp/inclusive prices không dùng cùng công thức. Chênh lệch là warning; không override source total.

Receipt required-for-approval: total. Invoice: total. Candidate field thiếu tên/date/number là warning. Nếu tài liệu không hợp profile hoặc user không xác nhận completeness thì không approve. Validation chạy lại trên corrected payload, không reuse issues từ prediction.

## 10. Versioning và schema files

Schema breaking change → `.v2`, model/dataset/evaluator updated cùng PR kế hoạch migration; additive fields vẫn cần client compatibility review. Manifest pin schema, normalizer, evidence mapper, OCR, model, tokenizer, processor và code commit.

`schemas/business.schema.json`: receipt/invoice payload. `schemas/extraction-result.schema.json`: result envelope + evidence/issues. `schemas/job-message.schema.json`: broker message. `schemas/export.schema.json`: approved business export. JSON Schema không tự kiểm FK, semantic date, quad geometry hoặc money arithmetic; cần validators tương ứng.

Source of truth lúc implementation: Pydantic contracts sinh JSON Schema/OpenAPI; files trong hồ sơ này là reference design. Không duy trì hai bộ model thủ công khác nhau mãi. Frontend types sinh từ OpenAPI, không tự viết lại API types.
