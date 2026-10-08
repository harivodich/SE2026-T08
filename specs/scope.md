# Scope v1

Reference đầy đủ: [scope/workflows gốc](../docs/design/v1/01-scope-workflows.md). Đây là requirement summary; chưa có implementation. Thiết kế đích Java/Thymeleaf + Python ở [architecture](../docs/architecture.md), [public API](contracts/public-api.md) và [compute API](contracts/compute-api.md); snapshot gốc chỉ đối chiếu.

## Input/output

- Vietnamese `receipt` hoặc `invoice`, type được operator chọn.
- JPEG, PNG hoặc PDF không mã hóa, chữ in, một trang.
- Field đơn và bảng tối đa 30 dòng. Thiếu/mơ hồ → null + issue; không cắt tài liệu ngoài profile âm thầm.
- Output model là prediction theo schema; output nghiệp vụ là JSON của revision đã human approve.
- Profile dự kiến: 20 MiB/file, canonical image ≤20 MP, job deadline 180s. Benchmark và khóa cấu hình sau spike tuần 2; các số này chưa được đo.

## Yêu cầu và acceptance

| ID | Yêu cầu | Evidence cần có khi implementation |
|---|---|---|
| FR-01 | Kiểm file/type/profile | Decoder/signature; corrupt/oversize/multipage fixtures |
| FR-02 | Background processing có status | 202; API responsive trong inference |
| FR-03 | OCR tiếng Việt và vị trí | Vietnamese text/rotation/canonical geometry tests |
| FR-04 | Schema extraction hai loại | Valid result + per-type holdout metrics |
| FR-05 | Table row relationships | Wrap/empty cells/30-row boundary |
| FR-06 | Không bịa field thiếu | Null/issue trên ambiguous/absent fixtures |
| FR-07 | Review fields/items | Save append revision |
| FR-08 | Chống overwrite | Two-tab race; stale save 409 |
| FR-09 | Approval đúng snapshot | Revalidate/current head/warning acknowledgement |
| FR-10 | Export approved revision | Unapproved 409; payload/checksum stable |
| FR-11 | Rerun không ghi đè | Candidate riêng; head không bị thay |
| FR-12 | Audit | Actor/time/action/base/new revision/reason |
| FR-13 | Retry idempotent | One committed run/job; fencing tests |
| FR-14 | Baseline/fine-tune tái lập | Manifest/config/hash/evaluator/per-type metrics |
| NFR-01 | Ownership access | Operator chỉ document của mình |
| NFR-02 | Logs không lộ payload | IDs/stage/error code; redaction tests |
| NFR-03 | Resource bounds | Byte/page/pixel/token/timeout; OOM không retry vô hạn |
| NFR-04 | Model rollback | Job pin release; activation chỉ đổi job mới |

## Non-goals

Handwriting, nhiều trang, tài liệu tổng quát, tự phân loại, chatbot, loại thứ ba, ERP thật, payment hoặc xác minh hóa đơn hợp lệ pháp lý. Không nhận PII thật vào demo. Public datasets chỉ dùng sau terms/provenance/PII audit; synthetic là nguồn main.

## Scope gate

G0/W2 hardware/model feasible; G1/W4 receipt E2E; G2/W6 hai loại + items; G3/W8 feature complete; G4/W10 quality/correctness; G5/W12 handoff. W13–16 là buffer/chất lượng, không tự mở thêm loại tài liệu. Xem [plan gốc](../docs/design/v1/05-delivery-plan.md).
