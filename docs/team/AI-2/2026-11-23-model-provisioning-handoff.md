> **Cập nhật model 23/11:** hiện chọn `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, Apache-2.0, 11 files và storage `artifacts/models/qwen/qwen3-1.7b/`. Input chỉ OCR text/layout. Các kết quả và thông tin Qwen2.5-VL bên dưới là evidence lịch sử trước khi đổi model; không chứng minh Qwen3 đã được tải/chạy. Kết quả kiểm mới ghi ở mục Qwen3 dưới đây. Quyền provision Lead vẫn chưa xác nhận.
# M1.2 — Docker Model Provisioning handoff

Ngày 23/11/2026. AI-2, base source `e040e94`, branch
`feature/AI2-M2_ai_service_docker`. Chưa commit/push/merge/deploy.

## Kết quả

Đã implement downloader/verify Qwen cố định model ID và revision
`66285546d2b821cf421d4f5eb2576359d3770cd3`. Image chứa công cụ, không weights.
Tái dùng `load_release` và existing manifest schema; inventory riêng ghi identity,
upstream checksum, local SHA-256, sizes và approval reference. Staging/resume,
bounded retries, lock, no-overwrite publication và read-only verify đã có source/tests.

**Thực tải model: BLOCKED.** Chưa có Lead confirmation về quyền provision và Qwen
Research License. Real model downloaded/verified/inference/G0: **NOT_RUN**.
Model root thật `artifacts/models/qwen/qwen2.5-vl-3b/` được Compose tạo rỗng khi
kiểm gate; không có snapshot Qwen được công bố. Không dùng fictional smoke làm
bằng chứng weights thật hoặc tự activate production.

## Files của increment này

| File | Thay đổi |
|---|---|
| [model_provision.py](../../../src/vietdoc/ml/model_provision.py) | Approval gate, fixed-pin Hub adapter, checksums/safetensors, staging, publication và offline CLI |
| [test_model_provision.py](../../../tests/unit/ml/test_model_provision.py) | Tiny fictional unit/regression tests, không download/GPU |
| [model-download.Dockerfile](../../../infra/model-download.Dockerfile) | Python3.12/HF CLI, non-root, no weights |
| [compose.ai.yaml](../../../infra/compose.ai.yaml) | `setup` service; models RO, checkpoint RW; model-offline flags |
| [ai-train.Dockerfile](../../../infra/ai-train.Dockerfile) | Checkpoint path/cache riêng, offline defaults |
| [ai-service.Dockerfile](../../../infra/ai-service.Dockerfile) | Runtime HF/Transformers offline defaults; B0 composition giữ nguyên |
| [infra/.env.example](../../../infra/.env.example) | Checkpoint path và approval/license variables để trống |
| [infra/README.md](../../../infra/README.md) | Download/verify/retry, storage/permissions, quarantine/rollback và giới hạn |

**Compose và Docker runtime changes cần Backend review.** Giữ nguyên OCR AI-1,
Data, Java, business/shared contracts, release schema, `.venv` và pyproject pins.
Các WIP tài liệu đã có từ trước không thuộc increment này và được giữ nguyên.

## Kiểm chứng thực chạy

| Check | Kết quả |
|---|---|
| Docker downloader build | PASS; build có `pip check` + `hf --help`, không gọi Hub model APIs |
| Compose config với setup/train/gpu | PASS; train/GPU giữ network none, `/models` RO và `/checkpoints` RW; inference Hub offline |
| Linux provisioning + release unit tests trên source cuối, network none | **52 passed, 0 skipped**, tiny fictional files |
| Windows full AI fixture gate trên source cuối | **837 passed, 455 subtests passed, 1 allowed symlink skip**, policy failures rỗng |
| Exact Compose setup command, approval/license để trống | PASS expected **exit2 BLOCKED_APPROVAL_AND_LICENSE_REQUIRED**, không tải weights |
| Docker Desktop Windows bind staging/verify/publication | PASS với tiny fictional files, fallback exclusive copy + manifest cuối |
| Downloader image offline verify qua base RO mount | PASS, cố ghi base bị từ chối; checkpoint ghi được và tồn tại trên host sau `--rm` |
| HF library interface/pin, không Torch trong downloader image | PASS offline; actual network metadata/weight transport chưa chạy |
| `git diff --check` | PASS |

Full AI fixture gate không chứa native suite, không chứng minh chất lượng OCR/Qwen.
Linux unit tests dùng image pytest đã có `vietdoc-ai-service:ai2-w1-w4-test`, mount
source hiện tại read-only và `PYTHONPATH=/workspace/src`; không dùng installed source
cũ để kiểm code mới. Windows thiếu symlink privilege dùng policy skip duy nhất có sẵn
ở `test_release_manifest`; test mới không bổ sung allowed skip.

Commands chính đã chạy từ repo root (Python env/contract paths đã thiết lập):

```powershell
docker build -f infra/model-download.Dockerfile -t vietdoc-model-download:dev .
docker compose -f infra/compose.ai.yaml --profile setup --profile train --profile gpu config --quiet
docker compose -f infra/compose.ai.yaml --profile setup run --rm --build model-download
.\.venv\Scripts\python.exe -B -m scripts.ci.ai --allow-windows-symlink-skip --junitxml=.verification/qwen-provision-ai-final.xml
docker run --rm --network none --mount "type=bind,source=E:\OCR_SE,target=/workspace,readonly" --workdir /tmp --env PYTHONPATH=/workspace/src --entrypoint python vietdoc-ai-service:ai2-w1-w4-test -B -m pytest -q -p no:cacheprovider /workspace/tests/unit/ml/test_model_provision.py /workspace/tests/unit/ml/test_release_manifest.py
git diff --check
```

Lệnh setup phía trên đã chạy với cả hai approval env vars trống và được kiểm
expected exit2; không phải successful download. Logs/JUnit nằm trong ignored
`.verification/`; fictional mount artifacts ở `.verification/qwen-provision-smoke/`,
hoàn toàn tách model root thật. Không còn container test chạy sau kiểm tra.

## Findings đã xử lý và giới hạn

- Build đầu lỗi CLI `ModuleNotFoundError: click`. Pin riêng downloader
  `huggingface_hub==1.2.1`, `typer-slim==0.20.0`, `click==8.1.8` rồi build/check CLI
  pass. Không sửa pins các môi trường hiện có. Các transitive deps chưa có lock
  toàn bộ; trước release cần lưu image digest và dependency inventory.
- Linux tmp filesystem hỗ trợ atomic `renameat2` nhưng Docker Desktop Windows bind
  trả EINVAL. Đã reproduce và thêm fallback reserve directory exclusive + file `xb`,
  manifest cuối, full verify; **không claim multi-file atomic/power-loss safety**.
  Partial final sau kill phải owner quarantine, không overwrite/recover mù quáng.
- HF LFS SHA-256 là checksum source của weights; files Git dùng Git blob SHA-1 để
  đối chiếu upstream, sau đó SHA-256 local cho tất cả files. Metadata lấy qua fixed
  Hub endpoint/revision sau approval; hashes không phải chữ ký xác thực owner.
- `ready` chỉ nghĩa offline pretrained snapshot verified, không phải service/model
  inference ready. Approval reference là record, không xác thực quyền Lead bằng crypto.
- Service giữ private HTTP network; HF/Transformers offline không là network firewall.
  Train/GPU profile network none. Không truyền HF token/approval sang consumer.
- Model bytes và real Hub transfer chưa kiểm. Disk/permission trên Linux của mỗi
  thành viên phải kiểm UID10001; checkpoint folder RW phải tách khỏi pretrained path.
- AI service/train Dockerfiles đã sửa env/mount compatibility; task đã build
  downloader, chưa rebuild/run Qwen hay GPU/training images để claim model compatibility.

## Unblock download

Lead cung cấp reference xác nhận provision và intended research/evaluation/license
conditions; người vận hành theo [runbook](../../../infra/README.md), đặt approval
reference thật cùng license ack rồi chạy setup. Sau đó phải giữ request/code/image
pins, inventory/manifest và verify-only exit0 trên actual bytes trước báo **Qwen
VERIFIED**. Download không tự cấp phép inference/training hoặc production activation.

## Kiểm tra mới sau đổi Qwen3-1.7B — 23/11/2026

- Windows focused tests model_provision/release_manifest: **55 passed, 1 skipped** (quyền symlink Windows).
- Linux Docker focused tests cùng source, network none: **56 passed**, không skip.
- Static YAML: **PASS** model/revision/tokenizer/11-file parity, OCR-only train/infer, thinking disabled, budgets, LoRA regex, business schema hash, execution guards.
- Compose setup/train/gpu config: **PASS**. Docker downloader build: **PASS**, không weights trong image. Docker context ban đầu bị file-lock; retry bằng endpoint `npipe:////./pipe/dockerDesktopLinuxEngine` thành công.
- Downloader image mới chạy với `--network none --read-only`: **expected exit2 BLOCKED_APPROVAL_AND_LICENSE_REQUIRED**, trả đúng Qwen3 ID/revision; không tải weights.
- `git diff --check`: **PASS**. Full AI fixture gate chưa chạy lại cho lần đổi model; số 837 ở trên là lịch sử.
- Thư mục model mới: `artifacts/models/qwen/qwen3-1.7b/<revision>/`; không chạm storage model cũ. Model thực tế **NOT_DOWNLOADED / NOT_VERIFIED**. Inference/training/GPU **NOT_RUN**.
- Shared Compose và ghi chú yêu cầu model mới trên Proposed ADR cần Backend/Lead review. Không đổi status ADR, shared schemas, AI-1 hoặc B0 runtime; không commit/push/deploy.

## Native provisioning cập nhật ngày24/11

Người dùng đã xác nhận Lead duyệt; Qwen3-1.7B revision70d244cc86ccca08cf5af4e1e306ecf908b1ad5e đã download đủ11 files bằng Docker và VERIFIED/READY, kiểm lại offline trên host PASS. Đã sửa verifier xử lý tokenizer.json dạng Git LFS bằng content SHA-256, không bỏ qua checksum; retry giữ staging và metadata cũ. Xem [M1.2 native handoff](2026-11-24-qwen3-inference-handoff.md). Không tự activate production; native schema PASS nhưng extraction semantic chưa nghiệm thu.
