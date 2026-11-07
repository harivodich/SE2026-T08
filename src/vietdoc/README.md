# Python AI/Data source

Đã có Data generator/fixtures; AI-1 loader/preprocess, geometry/evidence và Paddle
detector + Tesseract `vie`, OCR artifact v1/v2 opt-in theo
[proposal AI-1](../../docs/ocr-input-proposal.md). Entrypoint `recognize_document`
chia sẻ deadline và quản lý lifetime ảnh.

AI-2 đã có compute contracts (`contracts/compute.py`), release verifier
(`ml/release_manifest.py`), normalizer `vi-VND.v2`, strict output parser,
B0 `vi-label-header-b0.v3` cùng N1/N2 regressions, JSON logging, private FastAPI
service shell và env report CLI. Native OCR → extraction → compute response chưa
được compose vào service; default vẫn `AI_NOT_READY`. Python chỉ computation và
offline Data/ML; Java quản lý business state. Docker: [infra](../../infra/README.md).

Core package không cài dependencies. Chọn extra trong môi trường mới, từ repo root:

| Mục đích | Lệnh cài | Validator |
|---|---|---|
| Data renderer | `python -m pip install '.[data]'` | jsonschema 4.10.3; giữ Pillow 10.2.0 và fingerprint cũ |
| Compute contracts độc lập | `python -m pip install '.[contracts]'` | jsonschema 4.26.0 + referencing 0.37.0 |
| AI-1 loader | `python -m pip install '.[ai1]'` | Pillow12.0.0, pypdfium2_5.14.0; không load model |
| AI-1 native OCR | `python -m pip install '.[ai1-ocr]'` | 10 runtime pins, model provision riêng |
| Serving và AI tests | `python -m pip install '.[serve,test]'` | cùng validator hiện đại |
| Training | `python -m pip install '.[train]'` | cùng validator hiện đại; torch theo wheel index phù hợp |

Data và AI dùng môi trường riêng; không cài gộp `data` với `contracts`/`serve`/`train` vì pins validator/Pillow khác nhau. `test` chỉ cung cấp test runner/client, cần đi cùng extra của suite. Validator pins được khai báo trực tiếp trong `contracts`/`serve`/`train` để Docker cài dependency layer khi chưa có application source.

Fixture CI kết hợp AI1/AI2 dùng env riêng: `pip install '.[serve,test,ai1]' numpy==2.2.6`,
`pip check`, đặt `VIETDOC_CONTRACTS_DIR` tới `specs/contracts`, rồi
`python -m scripts.ci.ai`. Native smoke ở `tests/native/ocr/`, không thuộc fixture
gate; dùng env `ai1-ocr` đã provision model/font + `pytest==9.1.1` để chạy
`python -m pytest -q tests/native/ocr`. Không có model/font thì native NOT_RUN,
không coi opt-in skips hoặc collect-only là native PASS. Xem [tests](../../tests/README.md).

Normalizer v2 giữ chính xác các chữ số, không phụ thuộc decimal precision context. Chuỗi số nguồn tối đa 64 Ki ký tự; độ dài canonical (kể cả dấu chấm và zeros) tối đa 32 ký tự được kiểm trước khi mở rộng exponent. Giá trị ngoài bounds trả null + invalid outcome; zero chuẩn hóa thành `"0"`. Quy tắc locale tiền/quantity/ngày/giờ giữ nguyên. Output cũ mang version v1 giữ nguyên provenance; báo cáo/model manifest mới phải ghi v2, không so kết quả khác normalizer như cùng policy.


| Vùng active | Owner và output |
|---|---|
| contracts/ | AI-1 OCR/page, AI-2 compute typed adapters; shared JSON schemas ở specs/contracts |
| pipeline/preprocess.py,geometry.py,evidence.py,ocr/ | AI-1 canonical/preprocess/OCR/source regions |
| pipeline/extraction/,normalization.py,confidence.py | AI-2 extraction/fine-tune adapter/normalization/calibration |
| pipeline/service.py | AI-2 wiring, AI-1 review, không business services |
| entrypoints/api/,api/routes/ | AI-2 private compute/health, không public review API |
| infrastructure/storage/ | AI-2 attempt artifacts, no originals/exports/business DB |
| data/,evaluation/ | Data generator/gold/splits/metrics/reports |
| ml/ | AI-2 train/loading/release configs; no automatic activation |
| entrypoints/cli/ | Data offline data/eval commands; AI-2 training/model CLI |

`identity/documents/jobs/review/exports`, `infrastructure/persistence/queue`, `entrypoints/worker/dispatcher` là legacy scaffold: không implementation mới, Java target ở [backend](../../backend/SPEC.md). Chưa xóa placeholders trong lượt thiết kế.

Python server được phép load model theo lifecycle trong process riêng; Java web API không load weights. Python không DB credentials, claim/cancel business jobs hoặc approve/export. Contracts không import API/model frameworks.

Mở SPEC ngay folder định sửa, [doc vai trò](../../docs/team/README.md), [compute protocol](../../specs/contracts/compute-api.md). Big outputs ở ignored datasets/artifacts/runtime, chỉ tiny fictional fixtures có review vào Git.

## Chạy loader AI-1

Từ repository root, dùng Python ≥3.11 và PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ai1]"
```

API nhận bytes; không nhận đường dẫn từ request. Ví dụ trong Python đã cài package:

```python
from pathlib import Path
from vietdoc.pipeline.preprocess import load_document

# Đường dẫn do người chạy chọn ở local, không lấy trực tiếp từ HTTP request.
with load_document(Path("sample.png").read_bytes(), remaining_budget_ms=30000) as page:
    print(page.metadata.to_dict())
    page.canonical.save("canonical.png")
    page.processed.save("processed.png")
```

`canonical` là ảnh viewer phải dùng; `processed` là ảnh đưa cho OCR. Metadata chứa
matrix processed→canonical theo pixel-edge convention. `PreprocessLimits` cấu hình
bytes/pixels/resize/DPI/timeout; `PreprocessError.code` là lỗi typed. Loader trả ảnh/metadata; adapter bên dưới trả text/boxes. Transcript chỉ dùng đối chiếu.

## Chạy OCR AI-1

Đã smoke trên Windows 11 x64, Python 3.13.7, CPU. Core package không tự tải model;
extra `ai1-ocr` pin runtime đã chạy. Các platform/native Tesseract khác chưa được xác minh.
Từ repository root sau khi tạo `.venv`:

```powershell
$env:PIP_CACHE_DIR = Join-Path $PWD "artifacts/models/.pip-cache"
.\.venv\Scripts\python.exe -m pip install -e ".[ai1-ocr]"
$modelRoot = Join-Path $PWD "artifacts/models/ocr-v1"
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"
$env:PADDLE_PDX_CACHE_HOME = Join-Path $PWD "artifacts/models/.cache"
$env:PADDLE_HOME = Join-Path $env:PADDLE_PDX_CACHE_HOME "paddle"
$env:HF_HOME = Join-Path $env:PADDLE_PDX_CACHE_HOME "huggingface"
$env:HF_HUB_OFFLINE = "1"

# Tải đúng hai model pretrained, kiểm hash; chỉ chạy khi setup.
.\.venv\Scripts\python.exe -m vietdoc.pipeline.ocr.paddle_adapter --model-root $modelRoot --download

# Đường dẫn local do người chạy chọn; không dùng trực tiếp từ HTTP request.
.\.venv\Scripts\python.exe -m vietdoc.pipeline.ocr.paddle_adapter tests/fixtures/ocr-vietnamese-source.png --processed-long-edge 400 --model-root $modelRoot --output-dir artifacts/evaluation/my-ocr-run
```

Chọn output directory mới mỗi lần. Có thể thêm `--transcript sample.txt` để so
text sau chuẩn hóa whitespace; không truyền transcript vào recognizer. Có thể
thêm `--processed-long-edge 400` để tái kiểm resize của smoke. Output gồm
`canonical.png`, `overlay.png`, `ocr.json`, `run.json` với timing/config/hash và
`preview.html` chứa ảnh/OCR/transcript để kiểm trực quan. Mở `preview.html` bằng
trình duyệt ngoài VS Code, chọn block trong danh sách hoặc vùng trên ảnh để xem
text, ID, score, pixel/normalized coordinates; có nút tất cả vùng/bật-tắt highlight.
File tự chứa, không cần server hoặc tải tài nguyên ngoài. Đây là local OCR report,
không phải Java business viewer.
`quad` trong `ocr.json` là canonical normalized coordinates; overlay dùng đúng
canonical pixels. Vùng là text detector tìm được; không chia grid.

AI-2 dùng `VietnameseOcrEngine(model_root).load()` khi startup và `close()` khi
shutdown. Entrypoint nhận bytes, engine đã load, remaining job budget và input hash:

```python
from vietdoc.pipeline.ocr import recognize_document
from vietdoc.pipeline.evidence import EvidenceRequest, match_evidence

with recognize_document(document_bytes, engine, remaining_budget_ms=budget_ms,
                        expected_sha256=input_sha256) as stage:
    canonical = stage.loaded.canonical  # Chỉ dùng/save ảnh bên trong with.
    ocr_page = stage.ocr                # Metadata bất biến, giữ được sau with.
    remaining_for_extraction = stage.remaining_budget_ms  # Live budget, không reset.
    # Sau khi AI-2 trả raw value, có thể gọi mapper ngay trong cùng context:
    evidence = match_evidence(ocr_page, EvidenceRequest(
        "/total_amount", raw_total_text, label_text="Tổng tiền",
    ), prepared=stage.loaded.metadata)
```

Entrypoint đóng cả hai ảnh khi thoát context hoặc decode/OCR/consumer lỗi, không
load/close engine của caller. Output sai canonical metadata trả OUTPUT_INVALID.
AI-2 owns extraction, attempt paths/artifact hashes và compute response; Backend
promote verified canonical assets trước khi viewer dùng. Model root do service
config quản lý, không lấy từ request. Load kiểm
exact package/native versions, model file set và SHA-256; load/inference offline.
Một engine giữ một slot, busy trả `OcrError.code=AI_BUSY`. Cùng một monotonic
deadline được kiểm trước detector, giữa các crops/native recognition calls và
trước khi trả canonical output. Khi một call trả về sau deadline, không bắt đầu
call tiếp theo. Slot vẫn giữ tới khi native call đang chạy thực sự trả về;
hard timeout/isolation của OCR thuộc lifecycle M2.3, chưa implement ở đây.

`score` là Tesseract `MeanTextConf()/100`, có provenance trong `ocr_version`;
không dùng làm field correctness confidence. Evidence mapper đã có exact/context
và label-row selection, chưa semantic table grouping hay API/server wiring.
Span nhiều blocks chỉ được chọn khi consumer cấp `context_block_ids` cho cùng
item/field; thứ tự IDs trong hint không thay page reading order. `label_text`
luôn yêu cầu `prepared`, kể cả có explicit IDs hoặc chỉ một exact candidate.
Occurrence trong block ghép có thể chặn false uniqueness nhưng không tạo
substring bbox; khi chưa xác định được nguồn, trả empty regions + SOURCE_* flag.
Artifact OCR nội bộ v2 đã có implementation/golden cases, bật riêng bằng
`VietnameseOcrEngine(model_root, artifact_version=2)`: giữ recognized blocks nonblank,
unreadable detections giữ ID/quad/reason/score; có status và review flags. Mặc định
v1 vẫn fail trang khi text rỗng, chờ AI-2/Backend nhận version/semantics. Không đưa
v2 lên shared wire schema hoặc coi warning là đủ để approve thiếu required fields.
Xem [hướng dẫn handoff và giới hạn](../../docs/ocr-input-proposal.md#bàn-giao-o-n--2026-11-02).

Offline D1 helper dùng engine do caller load một lần, export ảnh trong context và
hash encoded canonical bytes; ghi cả typed failure và missing input. CLI dùng
manifest đã hash, không truyền transcript/gold vào OCR:

```powershell
$env:PYTHONPATH='src'
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'
$env:PADDLE_PDX_CACHE_HOME="$PWD/artifacts/models/.cache"
$env:PADDLE_HOME="$PWD/artifacts/models/.cache/paddle"
$env:HF_HOME="$PWD/artifacts/models/.cache/huggingface"
$env:HF_HUB_OFFLINE='1'
& artifacts/models/.venv-ai1/Scripts/python.exe -B -m vietdoc.pipeline.ocr.handoff `
  --manifest tests/fixtures/d12/manifest.json --model-root artifacts/models/ocr-v1 `
  --output-dir artifacts/evaluation/d1-new-review --artifact-version 2
```

Preflight output identity dùng casefold trên mọi OS: `a1/A1` bị reject trước khi
tạo output hoặc gọi engine; ID hợp lệ vẫn giữ nguyên case trong path/report.

Manifest đọc binary đúng một lần với cap1MiB; parse UTF-8 JSON và SHA-256 dùng cùng
buffer. Reject duplicate keys/nonfinite JSON, version thiếu/rỗng, identity/selection
hoặc asset path sai trước side effects. CLI preflight trước khi load engine và dùng
lại snapshot đã kiểm; helper không gọi recognize khi preflight lỗi. File manifest
đổi sau snapshot không đổi version/samples/digest của lượt đang chạy. Không sửa
label/split/asset hashes hoặc đọc transcript/gold vào inference.

Local report `vietdoc.ocr-handoff.v2` thêm `report_version`, `run_status`
(`completed`/`aborted`) và `abort_code`. `completed` nghĩa đã accounting mọi ID,
không bảo đảm mọi sample thành công: CLI chỉ exit0 khi tất cả ok. Typed failure
vẫn thử sample sau; unexpected exception/bare MemoryError abort, sample còn lại
`not_run/BATCH_ABORTED`, không gọi engine. Counts luôn giữ đủ requested IDs khi
final report ghi được; `native_attempted` chỉ tăng tại engine call thật.
Port thiếu/non-callable hoặc lookup lỗi giữ `native_attempted=false`; lỗi vẫn vào
fatal accounting với stage OCR, không bị tính thành một inference attempt.

Stage là `input`/`preprocess`/`ocr`/`export`, hoặc `not_started` sau abort. I/O errors
giữ stage/code riêng; lỗi export từng sample vẫn vào accounting. Lỗi ghi `run.json`
thêm `record_write_error`; sample ok chuyển failed nếu không ghi được record.
CLI exit2 cho aborted/failed/missing/storage failure, chỉ in safe codes/counts và
`report_written`; final storage failure không được claim report đã ghi. Existing
output trả safe `OUTPUT_DIRECTORY_UNAVAILABLE`, không ghi đè. Đây là offline helper
policy, không production HTTP error contract; default OCR v1/shared schemas giữ nguyên.

Output directory phải mới; `ocr.json`, `prepared.json`, `canonical.png`, `processed.png`,
`overlay.png`, `preview.html`, `run.json` theo sample ID và report tổng. Browser mở
preview local để xem hình/IDs/score; HTML chưa là Java viewer acceptance. Với manifest
20 mẫu `datasets/manifests/d12-integration-v2.json`, chỉ dùng `--fixture-fallback` khi
muốn lấy hai PNG tiny đã có cùng SHA-256; 18 input thiếu vẫn `not_run`, không native
failure. Env AI-1 nằm trên D trong ignored artifacts, tách Data Pillow10.2.0 và
AI-2 training. Không đưa weights/env/runtime outputs vào Git; fixture native hư cấu
an toàn cho consumer review ở `tests/fixtures/ocr-d1-native-handoff.json`.
