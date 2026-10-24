# D1.1 — dictionary nội dung hư cấu v1

Authority: `specs/contracts/business.schema.json` (urn:vietdoc:business:v1),
`specs/scope.md`. Scope: receipt/invoice tiếng Việt, chữ in một trang, ≤30 rows.
Các convention raw dưới đây là đề xuất Data cho D1.1, cần Lead/AI/Backend review;
không thay shared schema hoặc tuyên bố L1.1 đã được consumer duyệt.

Business JSON không chứa type, status, raw, reason hay provenance. Type do người
sử dụng chọn, lưu ngoài payload. Tất cả keys bắt buộc có mặt; nullable không có
nghĩa được bỏ key. `items` là array, không null; `[]` chỉ khi đã xác nhận không có
dòng hàng. Không bỏ dòng vì có cell thiếu. Chưa annotate bảng thì phải ghi rõ
ngoài payload và loại khỏi đánh giá bảng; không diễn giải `[]` thành gold đầy đủ.

## Format và null chung

- T (text): giữ dấu tiếng Việt, Unicode NFC, trim biên, xuống dòng trong description
  chuyển thành một khoảng trắng khi chỉ là wrap bố cục. Không bỏ dấu, không sửa tên
  bằng suy đoán. Tối đa 500 ký tự. Không dùng chuỗi rỗng làm missing.
- D (date): raw `24/10/2026` → `2026-10-24`, ngày lịch hợp lệ. `01/02/26`
  không rõ năm/convention → null + reason ngoài payload, không đoán.
- H (time): raw `09h05`, `09:05:30` → `09:05`, `09:05:30`; giờ 00–23,
  phút/giây 00–59. Không suy timezone hoặc bịa seconds.
- M (money): raw `45.000 đ`, `45 000 VND` → `"45000"`; decimal string
  không âm, không leading zero, dấu chấm thập phân nếu có (`"12500.5"`).
  Không binary float, currency symbol, grouping hoặc exponent trong canonical.
- Q (quantity): raw `1,5` → `"1.5"`, `02` → `"2"`, cùng regex decimal với M.
  Raw `1.234` thiếu convention rõ ràng → null + reason, không tự chọn 1234/1.234.
- Không suy giá trị bằng phép tính: quantity thiếu không mặc định 1; total thiếu
  không cộng items; thuế/chiết khấu không in không mặc định 0. Số 0 chỉ khi có
  label/value rõ. Arithmetic dùng Decimal khi tạo dữ liệu, không là gold inference.

Mọi scalar/cell dùng quy tắc này: đọc chắc chắn → giá trị canonical; thiếu hoặc
mơ hồ → null. Reason/issue riêng mô tả mơ hồ, không thêm key business.

## Receipt

Paths là JSON Pointer từ root business payload. Ví dụ hợp lệ raw → canonical;
cột cuối chỉ rõ trường hợp null (ngoài quy tắc chung).

| Path | Ý nghĩa / label trên ảnh | Format và ví dụ hợp lệ | Missing / ambiguous → null |
|---|---|---|---|
| `/merchant_name` | Tên cửa hàng; `Cửa hàng`, logo chữ | T: `Quầy Hư Cấu Lá Biếc` → cùng text | Không có tên / hai tên không rõ chủ thể |
| `/merchant_address` | Địa chỉ cửa hàng; `Địa chỉ`, `Đ/c` | T: `Lô GIẢ-LẬP, khu phố Hư Cấu` | Không in / địa chỉ bị che |
| `/transaction_date` | Ngày giao dịch; `Ngày`, `Ngày bán` | D: `24/10/2026` → `2026-10-24` | Không in / ngày không hợp lệ |
| `/transaction_time` | Giờ giao dịch; `Giờ`, `Thời gian` | H: `09h05` → `09:05` | Không in / `25:70` |
| `/total_amount` | Tổng tiền phải trả; `Tổng cộng`, `Thanh toán` | M: `45.000 đ` → `45000` | Không in / nhiều tổng không rõ nghĩa |
| `/items` | Các dòng hàng theo thứ tự đọc; bảng `Tên hàng` | Array các LineItem bên dưới; 0–30 dòng | Không null; bảng chưa annotate không là empty gold |

## Invoice

| Path | Ý nghĩa / label trên ảnh | Format và ví dụ hợp lệ | Missing / ambiguous → null |
|---|---|---|---|
| `/invoice_number` | Số hóa đơn; `Số hóa đơn`, `Số` | T: `GIẢ-LẬP-1101-01` → cùng text; giữ zero đầu nếu có | Không in / nhầm số đơn hàng |
| `/issue_date` | Ngày lập; `Ngày lập hóa đơn` | D: `24/10/2026` → `2026-10-24` | Không in / chỉ có ngày giao hàng |
| `/seller_name` | Đơn vị bán; `Đơn vị bán hàng` | T: `Xưởng Hư Cấu Cánh Diều` | Không in / không rõ seller |
| `/buyer_name` | Đơn vị/người mua; `Tên người mua`, `Đơn vị mua hàng` | T: `Đơn vị Hư Cấu Mầm Nhỏ` | Trống / bị che; không dùng seller thay buyer |
| `/subtotal` | Tổng trước thuế và chiết khấu; `Cộng tiền hàng` | M: `138.000 đ` → `138000` | Không in; không suy tổng dòng |
| `/tax_amount` | Số tiền thuế; `Tiền thuế GTGT` | M: `10.000 đ` → `10000` | Chỉ in `10%` chưa phải tax amount |
| `/discount_amount` | Số tiền giảm; `Chiết khấu`, `Giảm giá` | M: `5.000 đ` → `5000` | Không in / chỉ có tỷ lệ |
| `/total_amount` | Tổng phải thanh toán; `Tổng thanh toán` | M: `143.000 đ` → `143000` | Không in / không phân biệt đã trả-còn nợ |
| `/items` | Các dòng hàng theo thứ tự đọc | Array LineItem; 0–30 dòng | Cùng quy tắc receipt |

## LineItem dùng chung hai loại

`i` là index từ 0; không có key index riêng trong payload.

| Path | Ý nghĩa / label trên ảnh | Format và ví dụ hợp lệ | Missing / ambiguous → null |
|---|---|---|---|
| `/items/i/description` | Tên/mô tả hàng; `Tên hàng`, `Diễn giải` | T: `Trà sen hư cấu` | Không đọc được tên; không lấy tên dòng khác |
| `/items/i/quantity` | Số lượng; `SL`, `Số lượng` | Q: `1,5` → `1.5` | Không in / bị che; không gán 1 |
| `/items/i/unit` | Đơn vị; `ĐVT` | T: `hộp`, `mét`, `kg` | Không in; không suy từ mô tả |
| `/items/i/unit_price` | Giá cho một đơn vị; `Đơn giá` | M: `32.000 đ` → `32000` | Không in / không xác định giá thuộc dòng |
| `/items/i/line_total` | Thành tiền dòng; `Thành tiền` | M: `48.000 đ` → `48000` | Không in; không nhân quantity × price để điền |

## Metadata labels tách riêng

`*.gold.json` chỉ business. `*.labels.json` là sidecar D1.1 (chưa là shared
manifest contract), map JSON Pointer từng scalar/cell → `{status, raw, reason}`.

| Status | Ý nghĩa | Business | Raw và đánh giá dự kiến |
|---|---|---|---|
| present | Có và đã annotate được nội dung đọc chắc | Canonical value | Raw đã biết; được chấm value |
| absent | Xác nhận không in field/cell | null | raw=null; false fill cần được phát hiện |
| obscured | Có vị trí/label nhưng bị che hoặc mơ hồ không đọc chắc | null | Raw một phần nếu biết, reason; không bịa value |
| unlabeled | Chưa annotate; không kết luận có/không | null placeholder | raw=null; loại khỏi value scoring, không coi null là gold absent |

Ambiguous chưa có status thứ năm: dùng obscured + reason để nêu không đọc/chọn
chắc chắn. Đây là convention cần consumer review. Không lấy prediction làm gold.
Metadata hiện chỉ là kịch bản nội dung, không chứng minh field đã xuất hiện trên
ảnh: D1.2 phải render rồi QA trạng thái/ảnh. Không có bbox/confidence giả.

## Tái tạo và giới hạn

Config: `generator/fake-values.json`; logic: `generator/values.py` (Python stdlib).
Từ repository root, tạo vào thư mục mới:

```sh
PYTHONPATH=src python3 -m vietdoc.data.generator.values --seed 1101 --output /tmp/vietdoc-d11-new
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data_values.py' -v
```

Bốn sample (hai mỗi type), mỗi mẫu ba rows, có quantity nguyên/phân số và nhiều
đơn vị, invoice có/không thuế/giảm giá. Seed/config/version phải giữ cùng nhau.
Sample `02` có absent, obscured, unlabeled; tiền tổng vẫn là số in độc lập, không
recompute từ các cell null. Mẫu `01` có tax/discount zero được in; mẫu `02` không
in tax/discount dù arithmetic nguồn có điều chỉnh. Không áp một arithmetic pattern
cho mọi chứng từ. Không renderer, transcript, images, evaluator hoặc dataset lớn.

Toàn bộ tên có dấu hiệu Hư Cấu, địa chỉ không là địa chỉ giao dịch, số hóa đơn có
prefix GIẢ-LẬP; không mã số thuế/điện thoại/định danh cá nhân/chữ ký/con dấu.
Fixtures là nội dung tiny synthetic để review, không holdout hay evidence OCR.
Lead/AI-1/AI-2/Backend cần review semantics subtotal/discount, convention raw,
ambiguity/status exclusions và parse gold. Chưa có evidence họ đã xác nhận.
