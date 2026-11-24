# Infrastructure đích

Backend owns Compose/build/runtime/runbooks; AI-2 review Python loader/GPU/capacity, AI-1 OCR dependencies. Java app/job-runner/postgres Compose chưa có (B7.1).

Target services: app (Java web + Thymeleaf), job-runner (cùng Java artifact, runner profile), ai-service (Python private compute), postgres. Không Redis/Celery/web React container. AI/DB private network; model readonly; Python attempt volume không writable originals/committed assets/exports; Java promotes verified copies và streams authorized committed assets.

Pin env/deps/images sau actual smoke; test CPU/GPU profile và readiness trước handoff. Không deploy/cài dịch vụ tự động từ thiết kế. [Architecture](../docs/architecture.md), [Backend B7.1](../docs/team/backend.md).

## AI-2 Python images (CPU)

| File | Nội dung |
|---|---|
| `ai-service.Dockerfile` | Private compute FastAPI, target `test` chạy Python AI/contract/architecture/API tests, target `runtime` non-root/read-only |
| `ai-train.Dockerfile` | Offline training env: torch CPU + transformers/peft; mặc định in env report |
| `model-download.Dockerfile` | Python + HF CLI và downloader/verify Qwen; không weights trong image |
| `compose.ai.yaml` | `ai-service` (loopback 8090) và `ai-train` (profile `train`, `network_mode: none`) |
| `.env.example` | Ports/limits/volume paths; không chứa secret |

Service cài `.[serve]`, training cài `.[train]`; cả hai khai báo validator hiện đại trực tiếp.
Target `test` cài thêm `.[test,ai1]` và NumPy2.2.6, kiểm `pip check` và chạy `scripts.ci.ai` gồm
pipeline/ML/contracts/architecture/API cùng CI runner/gate regressions. Linux không
cho unexpected skips; JUnit tại `/app/test-results/ai.xml` trong test image.
CI scripts chỉ được COPY vào test stage. Data render tests chạy riêng với `.[data]`
theo [Data README](../src/vietdoc/data/generator/README.md), không đưa pins
Pillow/jsonschema của renderer vào AI image.

CLI factory đã có concrete OCR/B0 pipeline. Minimal runtime image chỉ cài serve, chưa chứa native OCR deps/model release; thiếu cấu hình vẫn trả `503 AI_NOT_READY`. Chọn verified profile bằng `VIETDOC_PIPELINE_MANIFEST_ID`; native runtime/env và Java acceptance còn chờ theo [handoff W1–W4](../docs/team/AI-2/2026-11-16-w1-w4-handoff.md). Docker healthcheck chỉ dùng `/health/live`; fixture Linux test image không là native OCR evidence.

Chạy trên Windows (PowerShell, từ repo root, Docker Desktop đang chạy):

```powershell
# 1. Token dịch vụ: file local trong secrets/ (Git ignore), không đặt trong .env hay Compose
New-Item -ItemType Directory -Force secrets | Out-Null
python -c "import secrets,pathlib;pathlib.Path('secrets/ai_service_token').write_text(secrets.token_urlsafe(32))"

# 2. (tùy chọn) Copy-Item infra/.env.example infra/.env rồi sửa VIETDOC_MODELS_DIR...

# 3. Tests trong Linux image, rồi chạy service
docker build -f infra/ai-service.Dockerfile --target test .
docker compose -f infra/compose.ai.yaml up -d --build ai-service
curl.exe http://127.0.0.1:8090/health/live
curl.exe http://127.0.0.1:8090/health/ready
docker compose -f infra/compose.ai.yaml logs -f ai-service

# 4. Môi trường training (CPU) và report phần cứng/thư viện
docker compose -f infra/compose.ai.yaml --profile train run --rm ai-train

docker compose -f infra/compose.ai.yaml down
```

Model/checkpoint: mount `VIETDOC_MODELS_DIR` (mặc định `artifacts/models`, read-only cho service). Mỗi release là `<pipeline_manifest_id>/manifest.json` liệt kê path/sha256/size_bytes (format đề xuất trong `src/vietdoc/ml/release_manifest.py`, cần Lead/Backend duyệt). Release sai hash/size/path/symlink bị loại lúc startup và ghi vào log `release_errors`. Đổi weights cần restart service.

`ai-train` không có network để tránh tải model ngầm. Dùng `model-download` được cấp quyền riêng để provision; giữ `network_mode: none` cho training, không bật mạng để tải ngầm trong train process. Base `/models` read-only; checkpoints ghi ở `/checkpoints`, cache tạm tại `/tmp/huggingface`.

GPU (NVIDIA, Docker Desktop + WSL2): `docker compose -f infra/compose.ai.yaml --profile gpu run --rm ai-train-gpu`. Image `vietdoc-ai-train:cu126` (~11 GB) dùng torch `cu126` khớp driver 560.x; driver mới hơn có thể đặt `AI_TRAIN_TORCH_INDEX`. Đã kiểm trên RTX 4060 Laptop 8 GB: `cuda_available=true`, bf16 matmul+backward chạy. Chưa đo model thật, chưa có code training. Service inference vẫn CPU.

Logs: JSON lines ra stdout (`ts/level/logger/event` + IDs/status/code/duration), không ghi document text, payload hay token; Docker `json-file` xoay vòng 3×10 MB.

## M1.2 — Docker Qwen provisioning (AI-2; Compose cần Backend review)

Phạm vi này chỉ **tải và verify pretrained snapshot**, chưa phải inference smoke/G0.
`src/vietdoc/ml/model_provision.py` dùng lại `ml/release_manifest.py`; không sửa
release schema, OCR AI-1, B0, Java hoặc Data. Qwen chưa được tự activate vào service.

Model/revision được cố định trong code, không có CLI override:

```text
Qwen/Qwen3-1.7B
70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
```

### Quyền provision và license

**Mặc định chặn tải mới khi chưa có xác nhận Lead** về quyền provision và điều kiện
Apache-2.0 của Qwen3-1.7B. Image build, unit tests fictional và verify offline vẫn làm
được. Không đặt approval giả để vượt gate. Repo model public nên downloader không
cần HF token; không mount home/cache/credentials host, `token=False`, endpoint cố
định. Approval reference chỉ ghi lại quyết định, không có cơ chế xác thực chữ ký Lead.

Sau khi Lead thực sự xác nhận, người vận hành đặt hai biến trong PowerShell:

```powershell
# Thay bằng reference quyết định đã có thật; không chạy bước này khi chưa được duyệt.
$env:VIETDOC_QWEN_PROVISION_APPROVAL = '<Lead-decision-reference>'
$env:VIETDOC_QWEN_LICENSE_ACK = 'apache-2.0'
docker compose -f infra/compose.ai.yaml --profile setup run --rm --build model-download
```

Reference nhận 3–200 ký tự ASCII gồm chữ/số và `._:/#-`; không chứa secret/PII.
Qwen3-1.7B dùng Apache-2.0; giữ LICENSE, attribution và notices áp dụng khi phân phối. Không áp dụng giới hạn research-only của model VL cũ. Quyền provision của Lead vẫn cần xác nhận riêng.
[License pinned](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/LICENSE).

Khi chưa có snapshot và chưa có approval, lệnh Compose trên trả JSON `blocked`, exit **2**,
trước mọi Hub metadata/file request. Compose có thể tạo bind directory rỗng và
network trước khi entrypoint chạy; không có weights được tải. Snapshot đã verified có thể được reverify offline/idempotent mà không cần approval mới. `--verify-only`
không cần approval, không network và không ghi file:

```powershell
docker compose -f infra/compose.ai.yaml --profile setup run --rm --no-deps model-download --verify-only
```

### Storage, mount và checkpoints

| Host mặc định (repo root) | Container | Quyền |
|---|---|---|
| `artifacts/models/qwen/qwen3-1.7b/` | downloader `/provision` | read/write, chỉ setup |
| `artifacts/models/` | training `/models`, service `/models` | read-only |
| `artifacts/models/checkpoints/` | training `/checkpoints` | read/write riêng |
| `datasets/` | training `/datasets` | read-only |
| `artifacts/evaluation/` | training `/artifacts/evaluation` | read/write |

`VIETDOC_MODELS_DIR` thay model root cho cả downloader/train/service;
`VIETDOC_CHECKPOINTS_DIR` thay checkpoint root. Paths tương đối resolve theo
`infra/compose.ai.yaml`, không theo cwd shell. Checkpoints nằm trong ignored models
root nhưng không nằm trong pretrained revision directory. Không ghi checkpoint
vào `/models/qwen/...`; đặt run IDs riêng dưới `/checkpoints/<run-id>/`.

```text
artifacts/models/qwen/qwen3-1.7b/
  .provision.lock                   # exclusive lock khi đang provision
  provision-status.json             # quan sát attempt gần nhất, không là integrity authority
  .staging-<revision>/
    upstream.json                   # size + source hashes đúng pinned Hub revision
    download/                       # HF partial/cache + downloaded files để resume
    <revision>/                     # candidate đã verify trước publication
  <revision>/                       # pretrained snapshot được công bố
    config.json, tokenizer assets, LICENSE, README.md, ...
    model.safetensors.index.json
    model-00001-of-00002.safetensors
    model-00002-of-00002.safetensors
    inventory.json                  # identity/revision/source hashes/local SHA-256/approval ref
    manifest.json                   # existing release schema, không thêm top-level keys
```

Không có weights/cache/secrets trong Docker build context/image; Dockerfile chỉ
COPY các modules cần thiết. Không tự đổi `VIETDOC_PIPELINE_MANIFEST_ID` hoặc
`qwen-g0.yaml` để bật inference. `ai-service` chỉ discover release directories trực
tiếp dưới `/models`; nested pretrained snapshot này không tự trở thành active release.

UID/GID container là **10001:10001**. Windows Docker Desktop bind mount cần quyền
ghi folder host. Trên Linux, tạo model/checkpoint/output folders trước và cấp quyền
cho UID10001 (hoặc dùng ACL của nhóm); không `chmod -R 777`. Base snapshot chỉ được
đọc từ train/service. Checkpoint bind mount có thể cần sửa ownership trên host dù
image đã tạo `/checkpoints`; mount che ownership trong image.

### Verify và ý nghĩa trạng thái

1. Kiểm đúng model ID/revision upstream và allowlist 11 files; không tải `main`,
   arbitrary filename hoặc repo khác. Metadata chỉ được truy cập sau approval gate.
2. Tải vào staging bằng Hugging Face pinned client. So size và **upstream LFS
   SHA-256** cho mọi LFS asset, gồm cả `tokenizer.json`; file Git thông thường so **Git blob SHA-1** gồm blob header.
   Đây là cách Hub phân biệt ETags, không giả metadata small-file là SHA-256.
   Mọi file local đều được tính SHA-256 riêng để inventory/manifest và verify lại.
   [Hub checksums/cache](https://huggingface.co/docs/huggingface_hub/package_reference/file_download).
3. Kiểm safetensors index: đúng hai shards, tensor keys↔shards, header length,
   dtype/shape/data offsets và tổng bytes; không import torch hoặc load tensors/GPU.
4. Ghi `inventory.json`; manifest chuẩn liệt kê hashes/sizes của model files và
   inventory. Dùng `load_release` để revalidate trước/sau publication.
5. Publish không ghi đè: ưu tiên atomic no-replace directory rename. Docker Desktop
   bind mount có thể không hỗ trợ `renameat2(RENAME_NOREPLACE)`; fallback `mkdir`
   exclusive + copy từng file `xb`, manifest cuối cùng, rồi verify toàn snapshot.
   **Fallback không phải multi-file transaction/power-loss guarantee.** Interrupted
   publication để lại partial final không được coi READY; cần owner quarantine.

| State/output | Ý nghĩa |
|---|---|
| `blocked`, exit2 | Thiếu approval reference hoặc license acknowledgement; không gọi Hub |
| `downloading` | Đang xử lý staging, chưa có snapshot usable |
| `downloaded` | Đủ file bytes và per-file checks; chưa xong index/full snapshot checks |
| `verified` | Candidate qua source checksum, safetensors và existing release verifier |
| `ready` + `integrity=verified`, exit0 | Snapshot pretrained cuối đã verify, sẵn cho consumer offline đọc |
| `failed`, exit1 | Không thành công; kiểm output/verify-only, giữ staging để điều tra/retry |

`ready_scope=offline_pretrained_snapshot_only`, `production_active=false` luôn
được trả; **không có nghĩa Qwen inference/service ready hoặc G0 đã đạt**. Status
file có thể cũ sau mất điện/lỗi cuối; `--verify-only` kiểm bytes hiện tại mới là
nguồn kết luận integrity. Hash/inventory không chống người có quyền sửa đồng thời
cả code, metadata và files; storage phải owner-controlled và consumer mount RO.

### Retry, resume, rollback và troubleshooting

- Chạy lại cùng lệnh sau khi đã được duyệt: complete verified snapshot được hash
  lại offline rồi exit0, không download/mutate. Corrupt/missing final file → fail
  closed, không overwrite. Không dùng `--force` để ghi đè pretrained release.
- Download retry tối đa 3 lần/file, backoff ngắn; partial/cache và verified staging
  files giữ qua container removal. Lỗi checksum có thể force-refresh **staging**,
  không final. Cache/staging giữ thêm bản files: dành disk cho khoảng 2–3 bản weights
  khi copy fallback, cộng checkpoints; không coi image disk size là VRAM.
- Kill container có thể để `.provision.lock`. Chỉ owner xác nhận không còn writer
  mới gỡ **đúng file lock**, không tự recursive cleanup. Retry metadata corrupt cần
  kiểm/quarantine staging cụ thể; không nới verifier hoặc tự trust file sai.
- Nếu publication bị ngắt để lại final partial: dừng writers, xác minh path nằm
  trong model root, đổi tên directory đó sang tên quarantine mới (không overwrite),
  rồi retry từ staging. Không tự xóa/sửa một final đang được consumer dùng.
- Rollback inference là chọn lại verified production release cũ theo Lead/Backend;
  downloader không activate/rollback production. Hai revision khác nhau phải dùng
  directories khác nhau và đổi pin bằng code review. Không thêm flag revision tự do.
- `PermissionError`: kiểm host folder, UID/ACL, mount RO/RW. `PROVISION_LOCKED`: kiểm
  writer/lock. `PIN_MISMATCH`: không đổi sang `main`; kiểm source/Hub metadata.
  `DOWNLOAD_OR_CHECKSUM_FAILED`: kiểm mạng/disk/quota, retry giữ cache; logs không
  in raw upstream exceptions hoặc tokens. Verify thiếu snapshot → exit1 đúng dự kiến.
- Build đầu tiên từng gặp CLI thiếu Click do resolver chọn Typer mới; image này
  pin riêng `huggingface_hub=1.2.1`, `typer-slim=0.20.0`, `click=8.1.8`, có `pip check`
  và `hf --help` trong build. Không cài các pins này vào env OCR/training hiện tại.

### Offline và credentials

Downloader là one-shot profile `setup`, có network riêng và không là dependency của
train/service. Train và GPU profile giữ `network_mode: none`; service cần private
HTTP nên vẫn có network phục vụ API, nhưng `HF_HUB_OFFLINE=1` và
`TRANSFORMERS_OFFLINE=1` chặn model Hub access. Đây là model-offline, **không phải
firewall cấm mọi HTTP tùy ý trong service**. Không truyền downloader approval vars,
HF token hay Hub cache sang train/service; service token hiện có chỉ để auth compute.

### Kiểm thử và giới hạn evidence

Unit tests mới: `tests/unit/ml/test_model_provision.py`, tạo tiny fictional files
trong temporary directories, gồm two-shard safetensors giả có cấu trúc. Các tests
không là tải/verify weights Qwen thật hoặc model inference evidence. Chạy cùng
`test_release_manifest.py`; full AI gate tự collect thư mục `tests/unit/ml`.

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/unit/ml/test_model_provision.py tests/unit/ml/test_release_manifest.py
docker compose -f infra/compose.ai.yaml --profile setup --profile train --profile gpu config --quiet
docker build -f infra/model-download.Dockerfile -t vietdoc-model-download:dev .
```

Backend review: service setup mới, `/models` RO của train/GPU, `/checkpoints` RW,
HF offline env và checkpoint/cache path trong train Dockerfile. B0 composition,
Java, OCR source và shared release/contracts schema giữ nguyên. Kết quả thực chạy
và blockers của increment được ghi trong handoff; chỉ báo model VERIFIED sau
download thực và hash thực, không lấy fictional bind-mount smoke làm model thật.

### Docker inference Qwen3 riêng (M1.2)

`infra/qwen-inference.Dockerfile` dùng image riêng `vietdoc-qwen-inference:m12-cu126`;
không cài hoặc sửa `.venv`, không chứa model weights/OCR runtime/credentials. Giữ
Torch2.14.1, Transformers5.20.2, safetensors0.8.0 và contract pins hiện có;
PyYAML6.0.3 dùng cho CLI config trong image và extra `test` để kiểm runtime YAML thật. Build cần mạng để lấy packages, runtime
mặc định offline. Không thay B0/service production profile.

```powershell
docker build -f infra/qwen-inference.Dockerfile -t vietdoc-qwen-inference:m12-cu126 .
```

Chuẩn bị input directory riêng gồm config được duyệt, `specs/contracts/*.schema.json`
và `receipt/` hoặc `invoice/` chỉ chứa `ocr.json`, `prepared.json`, `provenance.json`.
Không đưa ảnh hoặc gold vào mount của model. Mount verified Qwen3 snapshot read-only,
output ignored directory riêng read/write; không chuyển approval/HF token vào runtime.
Ví dụ sau khi đã có input/config/weights được duyệt:

```powershell
$repo = (Resolve-Path .).Path
$nativeRoot = Join-Path $repo 'artifacts/evaluation/qwen3-m12-native-20261124'
docker run --rm --network none --gpus all --read-only --tmpfs /tmp:size=256m `
  --mount "type=bind,source=$repo/artifacts/models/qwen/qwen3-1.7b,target=/models,readonly" `
  --mount "type=bind,source=$nativeRoot/inputs,target=/inputs,readonly" `
  --mount "type=bind,source=$nativeRoot/qwen-runs,target=/results" `
  vietdoc-qwen-inference:m12-cu126 `
  --config /inputs/qwen-smoke-prompt-v2.yaml `
  --snapshot /models/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e `
  --ocr /inputs/receipt/ocr.json --prepared /inputs/receipt/prepared.json `
  --provenance /inputs/receipt/provenance.json --type receipt `
  --output-dir /results/receipt-cli --repeat 2 --timeout-seconds 180
```

Dùng config budget có version mới nếu tokenizer thực báo overflow; lưu nguyên failure
và token counts trước khi đổi. Không truncate hoặc làm rơi blocks/items. Config trong
Git vẫn tắt execution. Báo cáo native và điều kiện acceptance ở
[handoff M1.2](../docs/team/AI-2/2026-11-24-qwen3-inference-handoff.md).

Native smoke ngày24/11 đã được người dùng xác nhận Lead duyệt: snapshot VERIFIED và 4/4 JSON/schema PASS sau prompt fix. Semantic extraction vẫn chưa nghiệm thu (unsupported units/header-as-item); không dùng demo count để claim accuracy. Xem handoff M1.2 cho metrics và failure history.
