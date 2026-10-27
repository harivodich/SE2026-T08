# Infrastructure đích

Backend owns Compose/build/runtime/runbooks; AI-2 review Python loader/GPU/capacity, AI-1 OCR dependencies. Java app/job-runner/postgres Compose chưa có (B7.1).

Target services: app (Java web + Thymeleaf), job-runner (cùng Java artifact, runner profile), ai-service (Python private compute), postgres. Không Redis/Celery/web React container. AI/DB private network; model readonly; Python attempt volume không writable originals/committed assets/exports; Java promotes verified copies và streams authorized committed assets.

Pin env/deps/images sau actual smoke; test CPU/GPU profile và readiness trước handoff. Không deploy/cài dịch vụ tự động từ thiết kế. [Architecture](../docs/architecture.md), [Backend B7.1](../docs/team/backend.md).

## AI-2 Python images (CPU)

| File | Nội dung |
|---|---|
| `ai-service.Dockerfile` | Private compute FastAPI, target `test` chạy Python AI/contract/architecture/API tests, target `runtime` non-root/read-only |
| `ai-train.Dockerfile` | Offline training env: torch CPU + transformers/peft; mặc định in env report |
| `compose.ai.yaml` | `ai-service` (loopback 8090) và `ai-train` (profile `train`, `network_mode: none`) |
| `.env.example` | Ports/limits/volume paths; không chứa secret |

Service cài `.[serve]`, training cài `.[train]`; cả hai khai báo validator hiện đại trực tiếp. Target `test` cài thêm `.[test]` và chỉ chạy `tests/unit/pipeline`, `tests/unit/ml`, `tests/contract`, `tests/architecture`, `tests/integration/api`. Data render tests chạy riêng với `.[data]` theo [Data README](../src/vietdoc/data/generator/README.md), không đưa pins Pillow/jsonschema của renderer vào AI image.

Hiện trạng đã kiểm: service validate auth/limits/schema/hash/release rồi trả `503 AI_NOT_READY` vì chưa có pipeline OCR/extraction (M2.1/M2.3). `/health/ready` luôn 503 cho tới khi có pipeline; Docker healthcheck chỉ dùng `/health/live`. Java `AiClient` hiện gọi `/extract` với payload khác protocol nên chưa nối được với service này.

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

`ai-train` không có network để tránh tải model ngầm; tải model/dataset cần quyền task riêng (bỏ `network_mode` khi được duyệt).

GPU (NVIDIA, Docker Desktop + WSL2): `docker compose -f infra/compose.ai.yaml --profile gpu run --rm ai-train-gpu`. Image `vietdoc-ai-train:cu126` (~11 GB) dùng torch `cu126` khớp driver 560.x; driver mới hơn có thể đặt `AI_TRAIN_TORCH_INDEX`. Đã kiểm trên RTX 4060 Laptop 8 GB: `cuda_available=true`, bf16 matmul+backward chạy. Chưa đo model thật, chưa có code training. Service inference vẫn CPU.

Logs: JSON lines ra stdout (`ts/level/logger/event` + IDs/status/code/duration), không ghi document text, payload hay token; Docker `json-file` xoay vòng 3×10 MB.

