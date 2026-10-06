# Hướng dẫn giao việc cho team VietDoc

Mở SPEC.md ngay trong folder phụ trách, rồi doc cá nhân trong bảng dưới. Mỗi doc có roadmap tuần, task nhỏ/input/steps/output/acceptance, reviewer, Git Flow và checklist bàn giao. [SPEC của docs/team](SPEC.md) giải thích chính folder này; [workflow chung](workflow.md) giữ handoffs/gates, không plan cá nhân thứ hai.

Repo hiện có scaffold và thiết kế; các file implementation nêu trong hướng dẫn là file cần viết khi nhận việc. Chưa gán bốn username GitHub vào vai trò vì chưa có phân công thực tế.

## Từ ngữ dùng trong hướng dẫn

| Từ | Hiểu đơn giản |
|---|---|
| Contract | Format input/output chung để các phần nối được với nhau |
| Gold | Đáp án chuẩn đã kiểm tra, dùng so với model |
| Transcript | Toàn bộ chữ trên ảnh được ghi lại đúng, dùng kiểm OCR |
| Manifest | Danh mục sample IDs, file paths, nhãn, split và version |
| Baseline | Cách làm ban đầu đơn giản để so với model cải tiến |
| Fixture | Mẫu nhỏ biết trước input/output để kiểm code hoặc nối thử các phần |
| Canonical image | Ảnh chuẩn viewer hiển thị; mọi vị trí chữ cần quy về ảnh này |
| Quad | Bốn góc của vùng chữ trên ảnh |

## Gửi tài liệu nào cho ai?

| Vai trò | Bản hướng dẫn | Việc đầu tiên |
|---|---|---|
| Lead | [lead.md](lead.md) — 6 task nhỏ | L1.1/L1.2: scope, người nhận việc, interfaces |
| Data Engineer | [data-engineer.md](data-engineer.md) — 8 task nhỏ | D1.1/D1.2: dictionary, 20 tài liệu giả/gold |
| AI-1: preprocessing & OCR | [ai-1-ocr.md](ai-1-ocr.md) — 8 task nhỏ | O1.1/O1.2/O1.3: canonical/preprocess/OCR thật |
| AI-2: extraction & fine-tuning | [ai-2-extraction.md](ai-2-extraction.md) — 11 task nhỏ | M1.1/M1.2/M1.3: hardware/license/infer/train-step |
| Backend | [backend.md](backend.md) — 15 task nhỏ | B1.1/B1.2/B1.3: contracts/types/checks/app tối thiểu |

## Bài toán chung

Người dùng upload ảnh/PDF một trang tiếng Việt, chọn receipt hoặc invoice. Hệ thống đọc chữ, trích field/bảng, cho người dùng sửa và duyệt rồi xuất JSON. Scope và fields theo [specs](../../specs/scope.md), [schemas](../../specs/contracts/README.md), [approval policy](../../specs/approval-policy.md).

Ví dụ receipt giả có nội dung:

```text
CỬA HÀNG MẪU
Ngày: 06/10/2026
Cà phê    3 ly    15.000    45.000
Tổng tiền: 45.000
```

Business payload đúng cho ví dụ này:

```json
{
  "merchant_name": "CỬA HÀNG MẪU",
  "merchant_address": null,
  "transaction_date": "2026-10-06",
  "transaction_time": null,
  "total_amount": "45000",
  "items": [
    {
      "description": "Cà phê",
      "quantity": "3",
      "unit": "ly",
      "unit_price": "15000",
      "line_total": "45000"
    }
  ]
}
```

Đây là ví dụ thiết kế, không phải output model đã chạy. Data tạo ảnh và đáp án từ cùng dữ liệu giả; AI-1 đọc ảnh thành text/boxes; AI-2 chuyển image/OCR context thành payload; Backend đưa kết quả vào màn hình và lưu bản đã approve; Lead kiểm tra format, yêu cầu và tích hợp.

## Cần thống nhất trước khi tích hợp

| Bên bàn giao | Input → output | Bên nhận |
|---|---|---|
| Data | Giá trị giả/template → ảnh, gold JSON, transcript, manifest | Hai AI và Backend |
| AI-1 | Ảnh/PDF → canonical page, OCR text/quad/score/version | AI-2 và viewer Backend |
| AI-2 | Type + image/OCR context → prediction, issues, provenance | Pipeline/worker Backend |
| Backend | Prediction → revision, approval, export | Người dùng và Lead nghiệm thu |

Backend implement types trong `src/vietdoc/contracts/`; AI/Data đề xuất và review phần mình dùng. Thay key/type/geometry/version cần báo consumer và Lead trước merge. Consumer có thể dùng tiny fixtures đúng contract trong lúc provider chưa hoàn tất; fixtures không được report như kết quả AI thật.

## Thứ tự làm lần đầu

1. Lead chốt schema/interface draft; Backend viết contracts; Data chuẩn bị ảnh giả theo reference schema hiện có. Ba việc này có thể chạy song song.
2. Khi có vài ảnh và format OCR, AI-1 chạy preprocessing/OCR. AI-2 thử load/infer/train-step ngay tuần 1–2, đồng thời làm baseline trên fixture rồi thay bằng OCR thật. Không cần chờ đủ dataset lớn hoặc ứng dụng hoàn tất.
3. Backend nối upload/job với pipeline thật. Nhóm chạy một receipt từ upload đến review, approve và export.
4. Fine-tune pilot phải bắt đầu khoảng tuần 4 khi dữ liệu đủ điều kiện; Backend hoàn thiện invoice/UI và kiểm thử retry/concurrency song song. Mốc/task chi tiết ở doc từng người; gates ở [workflow](workflow.md).

## Ai viết phần tích hợp?

Phân công cụ thể đề xuất cho lần kickoff này: Backend viết lớp nối mỏng `pipeline/service.py` và worker; AI-1 bàn giao preprocessing/OCR/evidence; AI-2 bàn giao extraction/normalization/confidence/model loading. Hai AI review cách Backend gọi các stage. Lead xác nhận phân công trước khi giao việc; đây là phần làm rõ ownership tích hợp, không phải thay đổi kiến trúc.

Backend không viết lại thuật toán AI trong lớp nối. AI không ghi business DB, tạo revision hay quyết định approval. Data tạo gold và evaluator, AI-2 chuyển dataset sang format model; AI-1 không phải nhận luôn cả phần chuẩn bị training input của AI-2.

## Fields cần làm đúng

- Receipt: `merchant_name`, `merchant_address`, `transaction_date`, `transaction_time`, `total_amount`, `items`.
- Invoice: `invoice_number`, `issue_date`, `seller_name`, `buyer_name`, `subtotal`, `tax_amount`, `discount_amount`, `total_amount`, `items`.
- Mỗi item: `description`, `quantity`, `unit`, `unit_price`, `line_total`.
- Key luôn hiện diện theo schema; không đọc được thì value null và issue phù hợp. Tiền/quantity là decimal strings; `items` tối đa 30 dòng. Không tự thêm mã số thuế hay loại chứng từ thứ ba.

## Mỗi lần bàn giao

- Code chạy được trong module mình sở hữu, command/config và tiny sample tái hiện.
- Input/output mẫu, checks đã chạy và kết quả thực; lỗi còn gặp ghi theo sample ID.
- PR gắn một việc cụ thể, reviewer đúng consumer và Lead duyệt cuối theo [Git Flow](../git-flow.md).
- Dữ liệu lớn ở `datasets/`, weights ở `artifacts/models/`, output thí nghiệm ở `artifacts/evaluation/`; các folder này bị ignore. Chỉ commit code, manifest an toàn, tiny fictional fixtures và báo cáo đã review.

Khi giao task, ghi làm gì, ai làm, xong khi nào, input/version, reviewer và link subtask trong doc cá nhân. D/O/M/B/L là mã tra guide, chưa phải issue đã tạo. Tiến độ/evidence ở Issue/PR hoặc phiếu trực tiếp; không folder tasks, không mở toàn bộ backlog ngay.

## Git Flow và trạng thái giao việc

Feature/bug từ develop → PR develop → peer review → Lead duyệt/merge → consumer smoke. Không push thẳng main/develop, force-push hoặc stage data/weights/secrets. Lệnh thực hành ở [workflow](workflow.md), policy ở [Git Flow](../git-flow.md), reviewer theo doc cá nhân.

Repo đủ context để kickoff/giao task đầu tiên, chưa app/model chạy. Lead cần gán bốn username vào vai trò, xác nhận hardware/capacity/ownership lớp nối và quyết định ADR khi áp dụng. GitHub access/protection/CI cần kiểm tra riêng; đọc [audit local](../reviews/repository-readiness-2026-10-07.md) trước claim integration/release ready.
