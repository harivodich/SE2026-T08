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
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/unit/pipeline -p "test_*.py"
```

Chọn output directory chưa tồn tại. Font là tài nguyên local có glyph tiếng Việt,
không tự tải font; report ghi font SHA-256. 20 case được sinh từ **một trang giả**:
PNG/JPEG ×8 EXIF orientations, hai PDF rotations, blank và corrupt. Native tests
kiểm đúng text có dấu, số tiền, parse, canonical dimensions và overlap với ink bbox
được dựng độc lập (IoU≥0.45). Đây không phải 20 D1 documents hoặc CER đại diện.
`report.json` ghi mọi case/error/latency/memory; ảnh/JSON/overlay nằm trong ignored artifacts.

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
