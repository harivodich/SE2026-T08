# Tests ownership

Có OCR/page contracts, loader PNG/JPEG/PDF và OCR boundary tests. Native smoke gọi
model thật khi bật env; chưa có actual-provider app E2E, Java parity hoặc viewer integration.

Sau khi [cài extra ai1-ocr](../src/vietdoc/README.md#chạy-ocr-ai-1), chạy từ repository root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/contract -p test_ocr_contracts.py
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit/pipeline -p "test_*.py"
```

Mặc định native smoke bị skip, unit/contract checks không cần weights. Để chạy
20 case bằng pretrained engine thật, setup model/cache env theo Python README rồi:

```powershell
$env:VIETDOC_OCR_MODEL_ROOT = $modelRoot
$env:VIETDOC_OCR_TEST_FONT = "C:\Windows\Fonts\arial.ttf"
$env:VIETDOC_OCR_SMOKE_OUTPUT = Join-Path $PWD "artifacts/evaluation/native-ocr-run"
$env:VIETDOC_GEOMETRY_SMOKE_OUTPUT = Join-Path $PWD "artifacts/evaluation/native-geometry-run"
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit/pipeline -p "test_*.py"
```

Chọn output directory chưa tồn tại. Font là tài nguyên local có glyph tiếng Việt,
không tự tải font; report ghi font SHA-256. 20 case được sinh từ **một trang giả**:
PNG/JPEG ×8 EXIF orientations, hai PDF rotations, blank và corrupt. Native tests
kiểm đúng text có dấu, số tiền, parse, canonical dimensions và overlap với ink bbox
được dựng độc lập (IoU≥0.45). Đây không phải 20 D1 documents hoặc CER đại diện.
`report.json` ghi mọi case/error/latency/memory; ảnh/JSON/overlay nằm trong ignored artifacts.

Khi bật cùng model/font env, `test_geometry.py` chạy thêm 6 case từ **một trang giả**
có 7 vùng chữ ở hai cột, một mô tả xuống dòng: identity, resize, crop+resize,
90°/180°+resize và reflection. Test dựng LoadedPage có transform đã biết, không
thêm tự động crop/deskew vào loader. So text/order và polygon trên ink masks tạo
trước OCR (IoU≥0.40, ink coverage≥0.95), xuất vào geometry output directory riêng.
Hai output directories đều phải mới; không ghi đè kết quả lần chạy trước.

Trong geometry output có hai subdirectories: `geometry-base/` giữ bộ7 regions
trên; `repeated-values/` thêm dòng `Đã trả 40.000` để kiểm chọn đúng `Tổng tiền
40.000` trên cùng6 transforms. Bộ số lặp kiểm text/order, exact source quad/ID và
ink coverage≥0.95; IoU được report riêng vì box detector có thể rộng. Case IoU<0.40
được ghi trong `detector_bbox_iou_below_0_40`, không claim suite này đạt tight-box
quality. Ngưỡng IoU≥0.40 của geometry-base vẫn giữ nguyên.

Geometry unit checks dùng NumPy inverse làm oracle độc lập, round-trip tolerance
`1e-7` pixel; kiểm perspective/horizon/bounds/unavailable, matrix scalar invariance,
reading order sau downsize và tall/wrapped cells. Không có model env thì cả ba
native smoke tests bị skip; các geometry unit checks vẫn chạy.

`test_evidence.py` kiểm source matching độc lập, không cần weights: repeated
amounts/label context, wrapped description, missing text/geometry, Unicode và
observed OCR fixture. Native geometry smoke còn kiểm total field metadata trên
cả6 transforms và sinh `total-overlay.png` cạnh overlay toàn bộ OCR regions.
Matcher giữ từng source quad/ID; ambiguity không được biến thành selected box.
Khi có `PreparedPage`, nhãn duy nhất và đúng một candidate bên phải cùng processed
row có thể giải quyết số lặp; hai candidates cùng row hoặc geometry thiếu vẫn
ambiguous. Unit checks có resize/rotated/reflected viewer và wrong-frame rejection.
Label/row constraint cũng áp dụng cho unique candidate khi cấp PreparedPage +
label_text: wrong-row/wrong-side hoặc thiếu label geometry không được matched.
Geometry regressions có loader thật2007→2000 và503×1000, boundary round-trips sau
resize/rotate/reflection. Chỉ projection roundoff ≤16 ULP được snap sát biên;
raw input ngoài bounds và projection overflow thật vẫn phải reject.

Entrypoint `recognize_document` được native20 case gọi trực tiếp. Stage checks
trong test_paddle_adapter.py kiểm live budget không reset, đóng cả hai ảnh khi
engine/consumer lỗi hoặc timeout, reject sai canonical metadata, và giữ engine
lifecycle với caller. `test_ocr_preview.py` kiểm ảnh PNG nhúng đúng pixels,
OCR/transcript được giữ nguyên, script-delimiter escaping và blank/unavailable.
Các checks HTML này không thay browser interaction/E2E. Preview được sinh bằng
CLI ở Python README và mở bằng trình duyệt ngoài VS Code.

Loader tests decode pixels thực, 8 EXIF tags, PDF rotation, resize/inverse,
byte/pixel/hash caps và kill/reap decode timeout. PDF encryption guard được inject
tại native API; chưa test file encrypted thật. Adapter unit tests kiểm resize,
rotate/reflection, unavailable, score/IDs, slot/lifecycle, vendor failures và
provisioning hash/archive/path checks. Fixture tests không là measured OCR quality.

- Java unit/integration/module/Flyway/DB/CAS tests ở backend/src/test/java, Backend owns.
- Python unit/pipeline/data/extraction/compute tests ở đây, provider owns.
- contract/: shared fixtures và cross-language parse; Backend + AI producers.
- e2e/: actual-provider upload→job→review→approve→export, browser conflict/CSRF/escaping.
- architecture/: Python no business DB imports, Java rules tại backend tests.
- fixtures/: tiny fictional audited data only.

Các Python business/queue/persistence test roots cũ là legacy, không đặt Java tests
vào đó. Commands/results/limits hiện có ở [proposal AI-1](../docs/ocr-input-proposal.md).
