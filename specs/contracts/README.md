# Contracts authoritative và adapters Java/Python

Schema Draft 2020-12 ở đây là contract trung lập cho thiết kế đích. Java DTO và Python models phải validate cùng schema/fixtures; Pydantic hay Jackson không được tự sinh bản khác rồi coi schema đổi là mặc định. Java hiện có adapter và OpenAPI riêng cho phần web; Python compute adapter chưa được tích hợp.

| Contract | Dùng ở đâu |
|---|---|
| [business](business.schema.json) | Receipt/invoice/line items, dataset gold/model/review/export |
| [extraction result](extraction-result.schema.json) | Prediction/evidence/issues/provenance; IDs do application cấp |
| [export](export.schema.json) | Approved revision JSON |
| [compute request](compute-request.schema.json) | Java runner metadata + original multipart bytes |
| [compute response](compute-response.schema.json) | Python result + attempt assets/canonical page |
| [compute error](compute-error.schema.json) | Stable private AI errors |
| [job message](job-message.schema.json) | Legacy broker schema, giữ compatibility; không dùng MVP mới |

[Java public API/Thymeleaf routes](public-api.md) và [shared fictional fixtures](../../tests/contract/README.md) là input implementation. [Compute protocol](compute-api.md) là nguồn cho transport/errors/semantic checks. [Approval policy](../approval-policy.md) là nguồn domain review. Java đã đóng gói OpenAPI public tại `../../backend/src/main/resources/openapi.json`; cần giữ examples/checks đồng bộ khi sửa API. Internal OpenAPI thuộc Python implementation ở M2.3. Hai API có boundary khác nhau.

## Rules và authority

- Type receipt/invoice; schema receipt.v1/invoice.v1; language vi. All business keys present, decimal strings/null,≤30items.
- Normalized canonical quad page0; confidence/evidence unavailable không tự bịa.
- Schema không kiểm ownership/state, date arithmetic, JSON Pointer existence, asset containment/hash/provenance correlation: owning validators cần tests riêng.
- URN refs đăng ký local registry; không auto fetch refs ngoài mạng.
- Shared schema PR trước consumers; breaking change version + data/model/evaluator/Java/Python/export compatibility.
- Backend owns schema/protocol/Java DTO; AI-1 OCR geometry types; AI-2 private compute types; Data gold validation. Lead review interface, không coding backlog.
- [Các ví dụ v1](../../docs/design/v1/examples/receipt.json) là dữ liệu giả, giữ nguyên. Snapshot không authority mới khi có mâu thuẫn stack.
- [Verification cũ](../../docs/reviews/verification-2026-10-07.md) kiểm schemas v1, không bằng chứng Java/Python API chạy. Kiểm mới được ghi trong báo cáo redesign.

## Backend adapter hiện có

Java `ContractValidator` đọc các schema đóng gói ở `../../backend/src/main/resources/contracts/` và map payload sang typed DTO. Đây là bản adapter của contract trung lập tại thư mục này, không phải nguồn schema mới. Bất kỳ thay đổi contract nào phải kiểm parity hai bản và cùng fixtures trước khi bật HTTP compute; Java client hiện vẫn bị gate.

`../../tests/fixtures/contracts/business-validation.json` là vectors synthetic cho receipt/invoice: null, unknown/missing key, ngày không tồn tại, boundary 30/31 items, kiểu sai ở business fields/line items, JSON number thay decimal string, và `schema_version` thiếu/sai. `BusinessContractTest` của backend đọc trực tiếp vectors này; Data/AI-2 có thể dùng chung khi triển khai consumer. Các fixtures không chứng minh OCR/model quality.
