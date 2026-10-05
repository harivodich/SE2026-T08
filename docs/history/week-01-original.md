# W1 — khóa contracts và chuẩn bị vertical slice

Đây là bản kế hoạch cũ được giữ để đối chiếu, không phải danh sách việc hiện tại. Team giao việc dần theo [tasks/README.md](../../tasks/README.md). [Plan 12–16 tuần](../design/v1/05-delivery-plan.md), [module ownership](../../AGENTS.md).

## Thứ tự tích hợp

Lead khóa scope → Backend contract PR → Data/OCR/extraction consumer fixtures → Backend wiring/upload → integration review. Dùng fixture theo contract để các IC không phải chờ full model; không report fixture như model accuracy thật.

## W1-LEAD — scope/contracts/ownership

- Owner: Lead. Depends: đọc thiết kế; xác nhận capacity/GPU còn thiếu.
- Deliverable: acceptance FR/NFR, contract review, dependency/PR order; chấp nhận hoặc sửa ADR Proposed có reason.
- Acceptance: receipt/invoice fields, row IDs, canonical geometry, missing labels và approval policy không mâu thuẫn; owners rõ, không giao backlog coding thường xuyên cho Lead.
- Reviewers: bốn IC xác nhận boundary mình dùng. Lead merge chỉ khi được người dùng yêu cầu và checks pass.

## W1-BE — contracts trước, bootstrap source vừa đủ

- Owner: Backend. Depends: W1-LEAD field contract; có thể review song song bằng reference schemas.
- Deliverable: source contracts Pydantic, schema/OpenAPI generation khi API tồn tại, focused positive/negative tests; minimal Python env/lock/CI phù hợp dependencies thật.
- Acceptance: payload hai loại, decimals/null, items/limits, result provenance và broker chỉ ID được kiểm; API/worker không load model trong API. Không copy toàn cây source thành file rỗng.
- Increment kế tiếp trong W1 nếu capacity đủ: migration/document metadata + bounded upload với tests; chưa dựng full job/model/review trong một PR lớn.
- Reviewers: Lead + AI/Data consumers. Schema PR merge trước wiring PR. Commands chạy thành công mới thêm README.

## W1-DATA — mẫu giả và manifest contract

- Owner: Data Engineer. Depends: business schema; draft có thể dùng reference v1.
- Deliverable: 10–20 tài liệu fictional, hai template mỗi type, schema-valid gold, source/base/template/family IDs và manifest proposal.
- Acceptance: rendered image khớp gold text/amount/rows, NFC, missing-label status rõ; variants cùng family/base cùng split. Không PII hoặc dùng OCR làm gold.
- Reviewers: AI-1/AI-2; Lead duyệt split. Public dataset audit chỉ nghiên cứu metadata/terms; download cần task riêng.

## W1-AI1 — OCR interface và geometry fixtures

- Owner: AI-1. Depends: OCR contract + tiny fictional samples.
- Deliverable: PreparedPage/OcrPage contract review, Vietnamese text/quad/score fixtures, kế hoạch OCR smoke và transform test.
- Acceptance: canonical viewer coords, page 0, [0,1], ordering/block IDs và unavailable geometry được biểu diễn; score không giả làm field confidence.
- Reviewers: AI-2 input contract, Backend viewer consumer, Lead boundary.

## W1-AI2 — extraction baseline/spike plan

- Owner: AI-2. Depends: business/OCR contract + hardware inventory.
- Deliverable: rule/model adapter contract review; model/license candidates và resource measurement protocol cho G0/W2.
- Acceptance: cùng schema với baseline, không hard-code duy nhất một layout; missing null, malformed output fail typed; plan infer + train-step + measured memory/latency/JSON validity trên 20 samples.
- Reviewers: AI-1 + Lead. Chưa hứa GPU/model name/accuracy trước spike; tải weights/train cần task được cấp quyền riêng.

## Integration review cuối W1

- Backend/Data/AI dùng cùng schema/version/fixtures; ghi disagreement thành issue trước merge.
- Có tiny integration fixture xuyên các interfaces, phân biệt với inference thật.
- Lead review diff, migration lineage, manifest IDs, data leakage và scope.
- Mỗi PR ghi tests đã chạy/kết quả và checks chưa chạy. Không tự push, mở PR hoặc deploy.

## Conflict policy

Backend serialize contracts/migrations/lockfile; regenerate generated files, không ghép lockfile bằng tay. Data owns immutable splits; AI-1 owns geometry; AI-2 owns model/prompt manifest. File owner resolve conflict hiểu cả hai thay đổi, rerun checks; không chọn ours/theirs toàn file. Lead quyết incompatible contracts trước merge.
