# Reference contracts v1

Các JSON Schema này sao chép nguyên trạng từ [snapshot thiết kế](../../docs/design/v1/README.md). Chưa có Pydantic models hoặc OpenAPI implementation; không duy trì hai bộ contracts thủ công khi code được tạo.

| Schema | Contract |
|---|---|
| [business](business.schema.json) | Receipt/invoice và line items |
| [extraction result](extraction-result.schema.json) | Prediction + evidence/issues/provenance |
| [job message](job-message.schema.json) | Broker chỉ message version/job ID |
| [export](export.schema.json) | Business envelope cho approved revision |

Chi tiết fields, API/error envelopes và ports: [contracts design](../../docs/design/v1/03-contracts.md). Ví dụ chỉ là dữ liệu giả: [receipt](../../docs/design/v1/examples/receipt.json), [invoice](../../docs/design/v1/examples/invoice.json), [result](../../docs/design/v1/examples/extraction-result.json), [export](../../docs/design/v1/examples/export.json).

## Rules

- `document_type=receipt|invoice`, schema `receipt.v1|invoice.v1`, language `vi`.
- All business keys hiện diện; string/null; tiền/quantity là decimal strings.
- Bbox là normalized quad canonical page 0; unavailable evidence/confidence không tự bịa.
- Structural schema không kiểm ownership/FK, approved state, ngày thực, JSON Pointer existence, arithmetic hoặc quad semantics: application validators cần làm riêng.
- `$ref` dùng URN nội bộ, validator phải đăng ký schemas, không tự fetch URL ngoài.
- Contract PR đi trước consumer PR. Breaking version change phải đồng bộ dataset/model/evaluator/frontend/exporter.
- Backend tạo Pydantic source-of-truth rồi generate JSON Schema/OpenAPI/types, thêm full validator positive/negative tests. Lượt bootstrap chưa chạy conforming JSON Schema compiler.
