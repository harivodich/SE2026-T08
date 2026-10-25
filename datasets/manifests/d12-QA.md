# D1.2 — integration set QA (2026-10-25)

Bộ dùng chung để team tích hợp, không phải untouched holdout. Không OCR/model output được dùng làm gold.

## Authority tại snapshot D1.2 ban đầu (fd741e6)

Không có `docs/team/data-engineer.md`, `data/generator/`, `templates/receipt/`, `templates/invoice/` hoặc các SPEC được yêu cầu trong checkout này. `datasets/processed/`, `datasets/manifests/`, `tests/fixtures/` cũng chưa có SPEC. Triển khai theo prompt D1.2, business schema, scope và D1.1 dictionary. Không tìm thấy proposal O1.1/B1.2. ADR-0006 vẫn Proposed. Chưa chốt shared page/geometry envelope, normalized quad mapping, reading order và consumer adapter. Không đổi trạng thái approval.

Checkout hiện tại đã merge guidance từ main (commit b5a6ee9), có `docs/team/` và SPEC theo folder; đã đọc lại trước khi sửa review. Các ghi nhận thiếu tài liệu bên trên là lịch sử của snapshot ban đầu, không phải trạng thái hiện tại. ADR-0006 vẫn Proposed; chưa có approval geometry/consumer mới.

## Strict review R01–R06 (25/10/2026)

- R01: D1 reads dùng UTF-8 tường minh, D1.1 writer LF; D1.2 JSON/transcript ghi bytes UTF-8/LF. D1.1 tests pass với harness default cp1252; D1.2 có test cp1252. Chưa chạy native Windows.
- R02: font test/CLI nhận `VIETDOC_DATA_FONT`/`--font`, có discovery và lỗi rõ nếu thiếu font/glyph. Portable test render với DejaVuSerif pass (chỉ skip canonical-only test). Test canonical bật `VIETDOC_CANONICAL_BYTES=1` pass với fingerprint được lưu ở tiny fixtures; không bỏ checks hash. Data render environment tách khỏi AI extras; chưa resolve chung với AI.
- R03: adapter renderer-local-v1 strip label prefix chính xác, group wrap liên tiếp và so toàn bộ từng occurrence. Negative controls ảnh/text 37.500/gold 0, 180.000/gold 80.000 và một repeated occurrence sai đều bị từ chối sau cập nhật hashes. PNG/text/box agreement vẫn cần visual audit, không suy ra từ sidecar equality.
- R04: manifest/sample shape/version, nhánh business theo type, schema ID, row/status counts, ID/lineage và asset set được kiểm. `--full-set` yêu cầu đủ 20 IDs/type/layout/row profiles; tiny loader vẫn hỗ trợ 2 mẫu. Seed/font/environment ghi provenance; generic loader không chứng minh nó thực sự là nguồn render. Loader D1.2 chỉ nhận present/absent; không nhận partial D1.1 để tránh biến null thành absent.
- R05: README có Bash/PowerShell setup và generate/verify cùng manifest mới. Đã chạy trên bản sao source sạch không có assets ignored cũ, với dependencies sẵn có; chưa thử fresh dependency installation hoặc Windows shell thật. Chưa có consumer AI/Backend chạy độc lập.
- R06: integrity dùng ValueError kèm sample ID thay cho asserts. Tests subprocess normal và -O đều từ chối hash/path/duplicate/transcript/bbox/missing file sai, input đúng pass.

Output mới: `datasets/processed/d12-review-fixed-v2/` (ignored), safe manifest `datasets/manifests/d12-integration-v2.json` (version d1.2.v2, có environment). 20 samples 10/10, 100 asset hashes khớp toàn bộ reference v1 trong môi trường canonical; không đổi gold/ảnh cũ để làm test xanh. Tiny v1 vẫn load được, không thêm environment giả cho bản lịch sử.

Checks trên branch PR #8: 6 D1.1 tests + 8 D1.2 tests, canonical bytes và portable font alternative; không gồm code/tests D2/D3. Native Windows và consumer AI/Backend handoff chưa chạy. Không claim CI hoặc API/model/browser pass.

### Commands kiểm chứng lượt sửa

```sh
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data_values.py' -v
PYTHONPATH=src VIETDOC_CANONICAL_BYTES=1 python3 -m unittest discover -s tests/unit -p 'test_data_integration.py' -v
PYTHONPATH=src VIETDOC_DATA_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf python3 -m unittest discover -s tests/unit -p 'test_data_integration.py' -v
PYTHONPATH=src python3 -O -m vietdoc.data.generator.integration --verify --full-set --manifest datasets/manifests/d12-integration-v2.json
```

Các mẫu tamper chỉ nằm trong temp directories của tests; fixtures/reference v1 không bị sửa. `git diff --check` sạch, assets v2 được xác nhận Git ignore. Các kết quả này không thay peer/Lead approval; chưa có gate consumer được duyệt.

## Kiểm tra tại snapshot D1.2 ban đầu

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
