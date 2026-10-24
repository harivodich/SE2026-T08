# D1.2 — integration set QA (2026-10-25)

Bộ dùng chung để team tích hợp, không phải untouched holdout. Không OCR/model output được dùng làm gold.

## Authority còn thiếu

Không có `docs/team/data-engineer.md`, `data/generator/`, `templates/receipt/`, `templates/invoice/` hoặc các SPEC được yêu cầu trong checkout này. `datasets/processed/`, `datasets/manifests/`, `tests/fixtures/` cũng chưa có SPEC. Triển khai theo prompt D1.2, business schema, scope và D1.1 dictionary. Không tìm thấy proposal O1.1/B1.2. ADR-0006 vẫn Proposed. Chưa chốt shared page/geometry envelope, normalized quad mapping, reading order và consumer adapter. Không đổi trạng thái approval.

## Kiểm tra đã thực hiện

- Mở năm contact sheets bao phủ cả 20 PNG; mở riêng PNG receipt-09 và invoice-10 để xem kỹ mẫu 30 rows. Dấu tiếng Việt đọc được, không thấy clipping hoặc chồng hàng; description dài wrap thành hai dòng. Trang ngắn còn nhiều khoảng trắng có chủ ý.
- Loader chạy trên 20 mẫu: decode PNG, hash/path, schema, label/raw từng scalar/cell, transcript từng draw call, boxes trong trang và field evidence. Đây là kiểm máy đối chiếu mọi row với nguồn render; chưa có người thứ hai đọc độc lập từng ký tự trên cả 20 ảnh.
- 8 unittest pass: D1.1 regression, coverage D1.2, tiny consumer, tái tạo byte hashes, chống overwrite, phát hiện corruption và transcript drift kể cả khi hash cập nhật.
- Không có sample fail trong checks đã chạy. Chưa đo OCR CER/KIE, chưa tích hợp API/model/viewer (repo chưa có consumer đó). Chưa audit độc lập bằng AI-1/AI-2/Backend.

## Theo sample ID

“OK” = loader đối chiếu mọi field/row + visual contact sheet; không có nghĩa team đã duyệt.

| Sample | Layout | Rows | Cases | QA |
|---|---|---:|---|---|
| d12-receipt-01 | receipt-layout-0-v1 | 1 | grouped money, repeated total, absent merchant_address, absent transaction_time | OK |
| d12-receipt-02 | receipt-layout-1-v1 | 1 | grouped money, repeated total | OK |
| d12-receipt-03 | receipt-layout-0-v1 | 3 | grouped money, repeated total, wrapped description | OK |
| d12-receipt-04 | receipt-layout-1-v1 | 3 | grouped money, repeated total, wrapped description, absent merchant_address, absent transaction_time | OK |
| d12-receipt-05 | receipt-layout-0-v1 | 5 | grouped money, repeated total, wrapped description | OK |
| d12-receipt-06 | receipt-layout-1-v1 | 5 | grouped money, repeated total, wrapped description | OK |
| d12-receipt-07 | receipt-layout-0-v1 | 12 | grouped money, repeated total, wrapped description, absent merchant_address, absent transaction_time | OK |
| d12-receipt-08 | receipt-layout-1-v1 | 12 | grouped money, repeated total, wrapped description | OK |
| d12-receipt-09 | receipt-layout-0-v1 | 30 | grouped money, repeated total, wrapped description, 30-row boundary | OK |
| d12-receipt-10 | receipt-layout-1-v1 | 30 | grouped money, repeated total, wrapped description, absent merchant_address, absent transaction_time, 30-row boundary | OK |
| d12-invoice-01 | invoice-layout-0-v1 | 1 | grouped money, repeated total, absent buyer_name | OK |
| d12-invoice-02 | invoice-layout-1-v1 | 1 | grouped money, repeated total | OK |
| d12-invoice-03 | invoice-layout-0-v1 | 3 | grouped money, repeated total, wrapped description | OK |
| d12-invoice-04 | invoice-layout-1-v1 | 3 | grouped money, repeated total, wrapped description, absent buyer_name | OK |
| d12-invoice-05 | invoice-layout-0-v1 | 5 | grouped money, repeated total, wrapped description | OK |
| d12-invoice-06 | invoice-layout-1-v1 | 5 | grouped money, repeated total, wrapped description | OK |
| d12-invoice-07 | invoice-layout-0-v1 | 12 | grouped money, repeated total, wrapped description, absent buyer_name | OK |
| d12-invoice-08 | invoice-layout-1-v1 | 12 | grouped money, repeated total, wrapped description | OK |
| d12-invoice-09 | invoice-layout-0-v1 | 30 | grouped money, repeated total, wrapped description, 30-row boundary | OK |
| d12-invoice-10 | invoice-layout-1-v1 | 30 | grouped money, repeated total, wrapped description, absent buyer_name, 30-row boundary | OK |

## Consumer review cần làm

- AI-1: duyệt convention renderer-local pixel boxes; mapping sang page/normalized quads, multiline và duplicate amount evidence. Boxes bao toàn text fragment (label + value đối với scalar), không phải token box. Không có inference confidence.
- AI-2: review gold normalization, status absent, thứ tự row và transcript reading order. Transcript dùng thứ tự logic draw calls: scalar → header → từng cell theo layout (description gồm mọi dòng wrap) → totals → repeated amount; không phải OCR output.
- Backend: load paths từ repository root, envelope ngoài business, thống nhất schema/type/page adapter cùng O1.1/B1.2. Loader ở generator là smoke consumer, chưa chứng minh API/viewer đã chạy.

## Counts

10 receipt + 10 invoice; 5 mẫu mỗi type/layout (4 templates). Mỗi type có 2 mẫu ở từng mức 1/3/5/12/30 rows. 16 mẫu wrap, 4 receipt thiếu address/time, 4 invoice thiếu buyer, 20 mẫu có grouped money và repeated total. Quantity 0,5 / 1,5 / 2 / 3; unit kg/mét/hộp/tập; invoice có tax/discount zero hoặc 10.000/5.000 đ. Tổng 204 business rows.
