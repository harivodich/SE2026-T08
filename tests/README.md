# Tests ownership

Baseline đã merge PR #4: `develop@9cfe29509bab8fa375c5e352ff90f5cf7c1ef7c9`.
Các số đo dưới đây là snapshots lịch sử trên source tương ứng, không thay kết quả
kiểm thử trên head mới của từng increment. Native suite hiện hành là
`tests/native/ocr`; discovery `tests/unit/pipeline` không chạy model thật.

PR4 candidate sau Backend CI và đồng bộ develop D3.2: fixture profile
`.[serve,test,ai1]` + `numpy==2.2.6` trên Python 3.12/Windows đã chạy
**720 collected, 719 passed, 389 subtests, 1 allowed Windows symlink skip**;
`pip check` sạch. Inventory bắt buộc 13 file AI2 + 7 file AI1; floor 720.
Hosted Linux phải chạy lại trên head PR mới và không cho skip. Native suite riêng.

PR4 candidate B (07/11/2026): native tests đã tách khỏi fixture discovery. Giữ nguyên
AST của `NativeGeometrySmokeTest` (2 methods/12 transforms) và `NativeOcrSmokeTest`
(1 method/20 format/error cases từ một trang synthetic) trong `tests/native/ocr/`.
Không import TestCase trở lại fixture; tên module native khác fixture modules.

Fixture env riêng: `pip install '.[serve,test,ai1]' numpy==2.2.6`, `pip check`, đặt
`VIETDOC_CONTRACTS_DIR` tới `specs/contracts`, rồi `python -m scripts.ci.ai`.
Windows không có quyền symlink chỉ dùng flag `--allow-windows-symlink-skip` đã có.
Candidate B thực chạy **667 passed,350 subtests,1 allowed symlink skip**, collect668;
gate exit0, không native skip. Collection toàn `tests/`685 tests không import
mismatch; collection không là execution. Inventory/CI còn thiếu tại snapshot B;
đã được Backend sửa trước khi PR #4 merge, như baseline ở đầu trang.

Native env riêng đã có pinned runtime/models/font, cài `pytest==9.1.1`, đặt
`VIETDOC_OCR_MODEL_ROOT`, `VIETDOC_OCR_TEST_FONT` tới paths thật rồi chạy
`python -m pytest -q tests/native/ocr`. Candidate B: **3 passed,32 subtests,
0 skipped**; JUnit/inventory local ignored ở `artifacts/evaluation/ai1-pr4-20261107/`.
Không cài native/model vào fixture env để chữa collection. Kết quả candidate B
không thay checks của head PR #4 đã merge hoặc increment sau đó.

Snapshot lịch sử 02/11/2026: **137 pipeline tests** (native bật, không skip) và
**24 OCR contract tests** qua trên Python3.13.7/Windows11. Schema9 và CI-gate11
tests qua riêng bằng validator local jsonschema4.25.1; không thay CI pin4.26.0.
Ba env trên D tách biệt: fixture `.venv-ai1-fixture`, native `.venv-ai1` và Data
`.venv-ai1-data`, đều dưới ignored `artifacts/models/`. Không gộp `.[data,ai1-ocr]`.
Fixture dùng `.[serve,test,ai1]` + `numpy==2.2.6`; từ repo root, env đã provision:

```powershell
$env:PYTHONPATH='src'
$env:VIETDOC_CONTRACTS_DIR=(Resolve-Path specs/contracts).Path
$fixturePython = Join-Path $PWD 'artifacts/models/.venv-ai1-fixture/Scripts/python.exe'
& $fixturePython -B -m pip check
# Chỉ dùng flag Windows khi thiếu quyền symlink đúng policy; Linux bỏ flag này.
& $fixturePython -B -m scripts.ci.ai --allow-windows-symlink-skip
```

New coverage: cross-block/currency occurrence guard, exact scoped wrap, partial
v2/nonblank IDs/strict migration/diagnostics, native failures remain typed,
missing-not-absent, local preview payload escaping, handoff lifetime/hash/error
denominator, independent renderer PNG identity/resize oracle, actual D2-size PDF
cap rejection. Native observed D1 fixture is review output, not OCR gold. Actual
AI-2/Backend consumer/approval/viewer acceptance, browser and encrypted-PDF E2E,
D3 metrics/native hang recovery vẫn pending; xem [report](../docs/ocr-input-proposal.md#bàn-giao-o-n--2026-11-02).

Có OCR/page contracts, loader PNG/JPEG/PDF và OCR boundary tests. Native smoke gọi
model thật khi bật env; chưa có actual-provider app E2E, Java parity hoặc viewer integration.

Chạy focused unit/contract checks bằng fixture env, không cần weights:

```powershell
& $fixturePython -B -m pytest -q tests/unit/pipeline tests/contract/test_ocr_contracts.py
```

Sau khi [provision native env riêng](../src/vietdoc/README.md#chạy-ocr-ai-1), chạy
20 synthetic format/error cases bằng pretrained engine thật. Không tải lại model
đã verify và không cài vào Data env. Native env cần `pytest==9.1.1`:

```powershell
$ocrPython = Join-Path $PWD 'artifacts/models/.venv-ai1/Scripts/python.exe'
$modelRoot = Join-Path $PWD 'artifacts/models/ocr-v1'
$env:PYTHONPATH=(Resolve-Path src).Path
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'
$env:PADDLE_PDX_CACHE_HOME=Join-Path $PWD 'artifacts/models/.cache'
$env:PADDLE_HOME=Join-Path $env:PADDLE_PDX_CACHE_HOME 'paddle'
$env:HF_HOME=Join-Path $env:PADDLE_PDX_CACHE_HOME 'huggingface'
$env:HF_HUB_OFFLINE='1'
$env:VIETDOC_OCR_MODEL_ROOT = $modelRoot
$env:VIETDOC_OCR_TEST_FONT = "C:\Windows\Fonts\arial.ttf"
$env:VIETDOC_OCR_SMOKE_OUTPUT = Join-Path $PWD "artifacts/evaluation/native-ocr-run"
$env:VIETDOC_GEOMETRY_SMOKE_OUTPUT = Join-Path $PWD "artifacts/evaluation/native-geometry-run"
& $ocrPython -B -m pip check
& $ocrPython -B -m pytest -q tests/native/ocr
```

Chọn output directory chưa tồn tại. Font là tài nguyên local có glyph tiếng Việt,
không tự tải font; report ghi font SHA-256. 20 case được sinh từ **một trang giả**:
PNG/JPEG ×8 EXIF orientations, hai PDF rotations, blank và corrupt. Native tests
kiểm đúng text có dấu, số tiền, parse, canonical dimensions và overlap với ink bbox
được dựng độc lập (IoU≥0.45). Đây không phải 20 D1 documents hoặc CER đại diện.
`report.json` ghi mọi case/error/latency/memory; ảnh/JSON/overlay nằm trong ignored artifacts.

Trong suite này, `test_native_geometry_smoke.py` chạy thêm 6 case từ **một trang giả**
có 7 vùng chữ ở hai cột, một mô tả xuống dòng: identity, resize, crop+resize,
90°/180°+resize và reflection. Test dựng LoadedPage có transform đã biết, không
thêm tự động crop/deskew vào loader. So text/order và polygon trên ink masks tạo
trước OCR (IoU≥0.40, ink coverage≥0.95), xuất vào geometry output directory riêng.
Hai output directories đều phải mới; không ghi đè kết quả lần chạy trước.

Kiểm môi trường lại ngày 09/11/2026 trên baseline `9cfe295` và increment B1/B2:
Windows 11 build26200, i7-12700H (14 cores/20 logical CPUs), RAM16GiB,
Python3.13.7, Paddle CPU4. Mười pins trong extra `ai1-ocr` khớp `pyproject.toml`;
Tesseract5.5.3; model set `ppocrv5-det-tess-vie-50446e5d01ac-b6b49293d95d`
được verify đúng file set/hash trong `paddle_adapter.MODELS`, không download.
Font Arial SHA-256 `b3658eadae55e682b5f69eb64c439c1ecc8f196c0bb8d4756d145d13bc86476a`.
Profile default: long edge2000, PDF200DPI, cap20MP, decode15s; geometry suite
có thêm transforms do test dựng. `pip check` của fixture/native/Data đều PASS.
Lệnh native ở trên thực chạy **3 passed,32 subtests,0 skipped**. Logs/JUnit,
runtime/model/font inventory và PNG/JSON outputs local ignored nằm dưới
`artifacts/evaluation/ai1-post-pr4-20261109/`; đây là synthetic smoke, không full
D1 hoặc CER/WER baseline. Handoff native20 vẫn cần archive Data được verifier nhận.

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
PR4 regressions còn kiểm exact amount + occurrence trong block ghép, một số lặp
hai lần trong cùng block và phân biệt `5.000` với `45.000`/`5.000.000`. Occurrence
chỉ để chặn false uniqueness, không tạo substring box. Span nhiều blocks cần
explicit item/description context; hai món/cột không liên quan không được ghép
thành matched. Label thiếu PreparedPage luôn có flag, không tự bỏ spatial check.
Geometry regressions có loader thật2007→2000 và503×1000, boundary round-trips sau
resize/rotate/reflection. Chỉ projection roundoff ≤16 ULP được snap sát biên;
raw input ngoài bounds và projection overflow thật vẫn phải reject.
Contract/geometry dùng chung matrix validation, kiểm global scales ±1e-200 và
±1e200, normalized projection và round-trip; không nới pixel bounds/tolerance.

Entrypoint `recognize_document` được native20 case gọi trực tiếp. Stage checks
trong test_paddle_adapter.py kiểm live budget không reset, đóng cả hai ảnh khi
engine/consumer lỗi hoặc timeout, reject sai canonical metadata, và giữ engine
lifecycle với caller. `test_ocr_preview.py` kiểm ảnh PNG nhúng đúng pixels,
OCR/transcript được giữ nguyên, script-delimiter escaping và blank/unavailable.
Các checks HTML này không thay browser interaction/E2E. Preview được sinh bằng
CLI ở Python README và mở bằng trình duyệt ngoài VS Code.
Composite predictor deadline regressions dùng fake monotonic clock và doubles:
detector/crop/SetImage/GetUTF8Text làm hết budget thì không bắt đầu bước native
tiếp theo, boundary là expired, Clear/slot cleanup vẫn chạy và publication không
reset budget. Đây là control-flow checks, không phải native latency benchmark.

Loader tests decode pixels thực, 8 EXIF tags, PDF rotation, resize/inverse,
byte/pixel/hash caps và kill/reap decode timeout. PDF encryption guard được inject
tại native API; chưa test file encrypted thật. Adapter unit tests kiểm resize,
rotate/reflection, unavailable, score/IDs, slot/lifecycle, vendor failures và
provisioning hash/archive/path checks. Fixture tests không là measured OCR quality.


Các test hiện chạy được gồm Java/H2/MockMvc trong `backend/src/test/java`, Node UI/API trong `backend/src/test/js`, và Python schema/Data/CI gate trong `tests/`. Chúng không chứng minh PostgreSQL race, actual Python provider hoặc OCR/model quality.

- Java unit/integration/Flyway/DB/CAS tests ở `backend/src/test/java`, Backend sở hữu. Shared business vectors ở `fixtures/contracts/business-validation.json`; chạy `./mvnw -Dtest=BusinessContractTest test` từ `backend/` (Windows: `mvnw.cmd`).
- `backend/src/test/js` kiểm các asset JavaScript ở `backend/src/main/resources/static`; dùng `node --test` từ `backend/src/test/js/`.
- Python unit/pipeline/data/extraction/compute tests ở đây, provider sở hữu.
- `contract/`: shared valid/invalid fixtures và cross-language parse; Backend + AI producers.
- `e2e/`: actual-provider upload→job→review→approve→export, browser two-tab/CSRF/escape khi provider sẵn sàng.
- `architecture/`: Python không import business DB; Java rules kiểm tại backend tests.
- `fixtures/`: chỉ tiny fictional audited data, không raw dataset hay weights.

`tests/unit/documents,jobs,review` và `integration/persistence,queue,storage` là legacy Python locations, không đặt Java tests tại đó. `integration/api` dành cho private Python compute, không phải public FastAPI business API. Đọc [architecture failure matrix](../docs/architecture.md) và [compute semantic checks](../specs/contracts/compute-api.md) khi mở rộng integration tests.
