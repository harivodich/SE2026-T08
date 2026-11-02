# Python AI/Data source

C? Data generator/fixtures v? OCR/page types, loader, geometry/evidence, Paddle detector + Tesseract `vie` theo [proposal AI-1](../../docs/ocr-input-proposal.md). Entrypoint `recognize_document` chia s? deadline v? qu?n l? lifetime ?nh. Ch?a actual extraction/service composition tr?n branch n?y. Python ch? Data/compute; Java qu?n l? business state.

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

Output directory phải mới; `ocr.json`, `prepared.json`, `canonical.png`, `processed.png`,
`overlay.png`, `preview.html`, `run.json` theo sample ID và report tổng. Browser mở
preview local để xem hình/IDs/score; HTML chưa là Java viewer acceptance. Với manifest
20 mẫu `datasets/manifests/d12-integration-v2.json`, chỉ dùng `--fixture-fallback` khi
muốn lấy hai PNG tiny đã có cùng SHA-256; 18 input thiếu vẫn `not_run`, không native
failure. Env AI-1 nằm trên D trong ignored artifacts, tách Data Pillow10.2.0 và
AI-2 training. Không đưa weights/env/runtime outputs vào Git; fixture native hư cấu
an toàn cho consumer review ở `tests/fixtures/ocr-d1-native-handoff.json`.
