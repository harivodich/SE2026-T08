# M1.2 — OCR Input Adapter & Qwen3 Model Loader

Ngày bàn giao: **24/11/2026**. Owner AI-2. **Đã chạy Qwen3 thật: raw/normalized schema 4/4 PASS; chất lượng extraction CHƯA NGHIỆM THU vì có giá trị không được OCR hỗ trợ và dòng bảng giả.**

Model đã download và verify; không còn blocker provision. Xem [native rerun bên dưới](#native-rerun-sau-khi-docker-desktop-được-bật-lại) và [báo cáo/artifacts local](../../../artifacts/evaluation/qwen3-m12-native-20261124/REPORT.md). Không coi schema PASS là field correctness hoặc production acceptance.

Trong phiên triển khai, theo yêu cầu người dùng đã fetch/merge `origin/develop` từ `e040e94` đến **`1f03d8d`** bằng fast-forward. Không conflict; hash xác nhận cả **29 file local chưa commit** giữ nguyên ngay sau merge. Các chỉnh sửa M1.2 tiếp theo được làm trên HEAD mới. Không commit/push/deploy.

## Source và kiến trúc

`AI-1 OcrPage + PreparedPage + caller-verified provenance → structured prompt → verified local Qwen3 → generated suffix → existing parser/vi-VND.v2 normalizer → selected business schema`.

| File | Trách nhiệm |
|---|---|
| [qwen_config.py](../../../src/vietdoc/ml/qwen_config.py) | Validated config consumer, model/tokenizer pin, execution guard, schema hash, device/dtype/budgets. Optional PyYAML reader hoặc API nhận mapping |
| [ocr_adapter.py](../../../src/vietdoc/ml/ocr_adapter.py) | Reuse bounded B0 consumer và AI-1 metadata validators; serialize text/IDs/order/quads/scores/diagnostics, selected type/schema, token budgets |
| [model_loading.py](../../../src/vietdoc/ml/model_loading.py) | Verify snapshot trước import frameworks; local-only AutoTokenizer/AutoModelForCausalLM, compatibility/preflight, explicit load/reuse/close, capacity1, deadline/OOM, provenance/metrics |
| [qwen_inference.py](../../../src/vietdoc/ml/qwen_inference.py) | Tách raw JSON syntax, raw selected-schema validity và normalized schema validity; raw/parsed results và typed failures |
| [qwen_smoke.py](../../../src/vietdoc/ml/qwen_smoke.py) | Opt-in offline CLI, private report trong thư mục mới, repeated generations và safe stdout; không download/train/service activation |
| [test_qwen_inference.py](../../../tests/unit/ml/test_qwen_inference.py) | Fictional OCR/model doubles: serializer/config/injection/budgets/lifecycle/compatibility/errors/parser/CLI |
| [qwen-g0.yaml](../../../src/vietdoc/ml/configs/qwen-g0.yaml), [configs README](../../../src/vietdoc/ml/configs/README.md), [feasibility](qwen-feasibility.md) | Cập nhật trạng thái consumer; execution vẫn tắt, training chưa chạy |

Reuse [model_provision.py](../../../src/vietdoc/ml/model_provision.py), [release verifier](../../../src/vietdoc/ml/release_manifest.py), [parser](../../../src/vietdoc/pipeline/extraction/output_parser.py), [business schema](../../../specs/contracts/business.schema.json). Không sửa source AI-1/Data/Backend/shared contracts/dependency pins hoặc B0/service/composition runtime.

## OCR và trust boundary

- OCR v1/v2, một trang receipt/invoice do caller chọn. Giữ nguyên thứ tự blocks; không sort theo ID, deduplicate text, nối bảng thành một dòng hoặc suy diễn quads. Text nhiều dòng và ký hiệu OCR ambiguity giữ nguyên; score là engine score, không phải correctness/confidence.
- Duplicate IDs, NaN/out-of-range/nonconvex geometry, mismatch canonical dimensions, unknown keys (kể cả gold transcript) và invalid Unicode bị reject. Unavailable geometry giữ null/reason; partial/unreadable diagnostics được giữ. Contract hiện không có per-block ambiguity enum, không tự thêm shared field.
- Missing OCR → `OCR_MISSING`; không blocks → `OCR_EMPTY` hoặc `OCR_UNREADABLE`, không trả null-filled success. Không model fallback sang ảnh. Partial có recognized blocks được xử lý với review flags.
- Hệ thống/prompt schema nằm trong system message; OCR nằm trong JSON user message. Escape special/role tokens nhưng JSON decode khôi phục đúng text. Đây là giảm injection surface, **không chứng minh LLM miễn nhiễm semantic prompt injection**; kết quả chỉ là candidate, chưa business acceptance.
- Tổng OCR serialized context và full chat template được đếm bằng tokenizer thật khi chạy loader; vượt cap → `CONTEXT_OVERFLOW`, không truncate. Defaults input3072/OCR1024/output2048/sequence5120. Prompt và token IDs có hash/provenance.
- `provenance.json` là **AI-2 local input metadata, không phải shared contract mới**; cần đúng bốn SHA-256 keys `input_sha256`, `canonical_sha256`, `engine_sha256`, `profile_sha256`. Caller phải xác minh asset identity/hashes, engine release manifest và profile trước bàn giao. Adapter kiểm shape/dimensions/format, **không thể tái kiểm encoded input/canonical bytes khi chỉ nhận OCR/layout**. `ocr_serialization_sha256`/`prepared_metadata_sha256` được tính trên canonical JSON serialization tại adapter, khác hash raw artifact bytes.

## Model, lifecycle và outputs

Model **`Qwen/Qwen3-1.7B`**, revision đọc từ config **`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`**; bắt buộc khớp pin downloader. Local verified snapshot dưới `artifacts/models/qwen/qwen3-1.7b/<revision>/`, không remote fallback. License Apache-2.0; xem [pinned model card](https://huggingface.co/Qwen/Qwen3-1.7B/tree/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e).

- `load()` verify toàn snapshot bằng cơ chế provisioning hiện có trước khi import Torch/Transformers. Check model type/context/vocab/EOS/template, requested CPU/CUDA/dtype, available memory lower bound. CPU chỉ float32; CUDA BF16 phải support. Không tự offload, đổi precision hoặc chạy QLoRA trong M1.2.
- `load()` lại khi ready tái sử dụng instance; nonblocking capacity1 cho load/generate/close, busy có typed error. OOM/backend failure làm loader failed và bỏ references; `load()` retry explicit. Không promise CUDA cache được giải phóng ngay.
- Official tokenizer template với `enable_thinking=False`; fresh deterministic greedy generation config, một beam, batch1. Đây không phải cam kết GPU bitwise determinism. Chỉ decode suffix sau prompt, giữ special tokens để phát hiện reasoning; không strip reasoning để hợp thức hóa output.
- Deadline cooperative tại token boundaries và kiểm trước/sau backend; không hard kill một GPU kernel đang block. Context overflow/OOM/timeout/load failure/malformed/truncated/invalid schema là lỗi nội bộ `MLFailure(code, stage)` hoặc `InferenceResult.error`, **không thêm enum HTTP dùng chung**.
- Raw-schema invalid luôn không có accepted `payload`, dù parser normalize được; `parsed_payload` chỉ cho diagnostics. Fence, numeric literal, extra/missing keys và wrong type không được biến thành raw-valid success. Không sinh runtime IDs, confidence/evidence hoặc ghi business state. Cần evidence/confidence/consumer review trước production wiring.

Provenance khi inference thật gồm model/config/schema/manifest/inventory hashes, package versions, device/dtype, OCR/preprocess serialization hashes, token counts, finish reason và timings. RAM RSS trên Linux, GPU allocated/process-peak khi available; unavailable là null. Host RAM preflight không thay cgroup/container checks và không bảo đảm fit. Chưa có performance/model hashes local thực trong task này.

## Lệnh kiểm và smoke

Các lệnh đã thực thi trong `.venv` hiện có:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$env:VIETDOC_CONTRACTS_DIR = (Resolve-Path specs/contracts).Path
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/unit/ml/test_qwen_inference.py
.\.venv\Scripts\python.exe -B -m scripts.ci.ai --allow-windows-symlink-skip --junitxml=.verification/qwen3-m12-ai-final.xml
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B -m vietdoc.ml.qwen_smoke --help
git diff --check
```

Sau approval và verified weights, trong **môi trường AI-2 inference đã được review** có Torch/Transformers/validator/PyYAML tương thích các pins hiện có, dùng local config copy được duyệt với `execution.enabled: true`. Không bật checked-in config hoặc production release âm thầm. Lệnh mẫu sau **chưa chạy native**, chạy riêng từng type với OCR thật tương ứng:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = '1'
python -B -m vietdoc.ml.qwen_smoke `
  --config artifacts/evaluation/m12-approved.yaml `
  --snapshot artifacts/models/qwen/qwen3-1.7b/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e `
  --ocr artifacts/evaluation/ai1-receipt/ocr.json `
  --prepared artifacts/evaluation/ai1-receipt/prepared.json `
  --provenance artifacts/evaluation/ai1-receipt/provenance.json `
  --type receipt --repeat 2 --timeout-seconds 60 `
  --output-dir artifacts/evaluation/qwen3-m12-receipt
```

Đổi sang OCR invoice, `--type invoice` và output directory mới cho mẫu còn lại. Không ghi đè report cũ. `report.json` chứa raw/parsed outputs riêng tư, cold load, first/subsequent-generation latency và metrics/provenance; stdout chỉ status an toàn. Không stdout/log raw OCR. Lệnh không có download, train hoặc production activation.

## Evidence offline ban đầu — trước native rerun

| Kiểm thực thi trên source cuối | Kết quả |
|---|---|
| Tests M1.2 riêng | **71 passed**; fictional OCR/model doubles, gồm connected receipt+invoice flow, model reuse và padded embedding vocabulary |
| Full AI fixture gate | **930 passed, 455 subtests, 1 allowed skip**; 931 collected, policy_failures rỗng, exit0, 44.49s |
| Data regression sau merge | **41 passed, 45 subtests**, không conflict với local AI-2 |
| `.venv` pip check | **No broken requirements found**; không có torch/transformers/PyYAML trong environment này |
| CLI `--help`, gồm Windows CP1252 | **PASS** |
| CLI chạy bằng config hiện tại trong `.venv` | **expected exit2 CONFIG_DEPENDENCY_MISSING**, `native_inference_attempted=false`, không tạo output |
| Config consumer dùng PyYAML có sẵn trong env riêng | **PASS**, đúng model/revision và `execution_enabled=false`; không load OCR/model frameworks |
| UTF-8 và local links | **PASS**, 20 local links |
| `git diff --check`, protected-source review | **PASS**; không sửa owning source AI-1/Data/Backend/shared contracts/B0 runtime/dependency pins |
| Linux Docker M1.2 tests | **NOT_RUN/BLOCKED**: daemon endpoint `dockerDesktopLinuxEngine` không tồn tại tại lúc chạy; không dùng kết quả Docker provisioning lịch sử để claim M1.2 |
| Qwen3 weights/native inference/performance/training | **NOT_DOWNLOADED / NOT_VERIFIED / NOT_RUN** |

Allowed skip duy nhất: `test_release_manifest.py::test_symlinked_file_is_rejected`, vì Windows không cấp quyền tạo symlink. JUnit/log ở ignored `.verification/qwen3-m12-ai-final.xml` và summary do CI script tạo. Tests fictional/doubles chỉ xác minh control flow, không là model/GPU/native OCR hoặc quality evidence. Không có performance numbers hoặc Qwen output thật để báo.

**Blockers tại thời điểm offline ban đầu, đã gỡ ở native rerun:** lúc đó chưa Lead provision confirmation, chưa snapshot Qwen3 đã verified; `.venv` **không cài torch/transformers/PyYAML**. Không thay `.venv`; native rerun dùng Docker inference riêng sau xác nhận approval của người dùng. Bảng offline trên là evidence lịch sử, không mô tả trạng thái model hiện tại.

Điều kiện chuyển M1.3: owner provision approval → verified snapshot → review isolated dependency/device/container environment → receipt+invoice OCR thật với provenance → native schema/errors/cold/warm/RAM/VRAM report → Lead nhận M1.2. Sau đó mới tiny full-label dataset/collator/masking và train-step/update/checkpoint/reload; không dùng fixture PASS làm G0.

## Native rerun sau khi Docker Desktop được bật lại

Người dùng xác nhận Lead đã duyệt provision/smoke. Inventory ghi reference `lead-approved-user-confirmation-20261124`, license ack `apache-2.0`; đây là xác nhận qua người dùng, không phải independent signed Lead approval. Docker downloader tải đúng **`Qwen/Qwen3-1.7B` @ `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`**, kiểm đủ 11 files, source SHA-256/Git hashes, local SHA-256, sizes và safetensors index. Snapshot cuối **VERIFIED/READY**; verify offline lại trên Windows host cũng PASS. Không tự activate production release.

[infra/qwen-inference.Dockerfile](../../../infra/qwen-inference.Dockerfile) tạo environment riêng, không chứa weights, không sửa `.venv`: Python3.12.15, Torch2.14.1+cu126, Transformers5.20.2, safetensors0.8.0, PyYAML6.0.3, CUDA12.6. RTX4060 Laptop8188MiB, driver560.94; BF16 matmul/pip check PASS. Runtime `--network none`, read-only root/model/input bind, output bind riêng, không HF token/downloader credentials; **không mount ảnh hoặc gold vào Qwen**.

AI-1 native CPU engine hiện có chạy mới trên `samples/receipt-demo.png` và `samples/invoice-demo.png`, tương ứng **10/13 observed blocks**, status complete. Giữ text/IDs/order/canonical quads/scores; cùng OCR JSON được dùng cho B0 và Qwen. Không dùng gold transcript, không sửa source OCR AI-1 hoặc Data.

### Token budget và các lỗi thực đã xử lý

- Tokenizer thực đo OCR1978/2668 tokens, vượt cap1024 ban đầu; full prompt cũ2637/3327 vượt input3072 ở invoice. Dùng artifact-local budget v2 **input4096 / OCR3072 / output2048 / sequence6144**, không truncate/drop blocks. Source G0 config vẫn disabled, chưa tự sync budget này vào training config.
- `tokenizer.json` thực tế là Git LFS: sửa downloader dùng upstream LFS SHA-256 cho cả non-weight assets, không dùng Git pointer blob hash làm content hash; resume staging sau test RED/GREEN, không bypass checksum.
- Transformers hiện trả BatchEncoding mặc định: adapter yêu cầu `return_dict=False`. Linux memory preflight dùng `MemAvailable`, gồm page cache thu hồi được, thay cho chỉ `MemFree`.
- Prompt đầu khiến model echo OCR envelope: **4/4 lượt v2 bị TRUNCATED_JSON**, giữ nguyên outputs/logs. Prompt `qwen3-business-json.v2` bổ sung response keys/task rõ ràng, chỉ dùng schema definitions reachable từ selected type; không thay shared schema, model, revision, OCR hoặc greedy decoding. Đây là debug trên cùng hai demos, không phải unseen benchmark.

### Số đo native với prompt v2

Một loader instance, 2 generations/type, `enable_thinking=False`, batch1, greedy, không LoRA/QLoRA/training. Cả 4 raw outputs kết thúc EOS, raw JSON + selected business schema + normalized schema PASS, normalization issues0. Hai lần chạy mỗi type trả cùng raw bytes.

| Type | Input/output tokens (output gồm EOS) | First/warm generation | Qwen scalar fields/item rows | B0 scalar fields/item rows |
|---|---|---|---|---|
| receipt | 2592/135 | 5.610s / 4.957s | 5 / 1 | 0 / 0 |
| invoice | 3309/240 | 8.640s / 8.383s | 8 / 2 | 0 / 0 |

Cold process load **87.653s**, gồm full snapshot verification, framework import và model initialization; không purge filesystem cache. Process peak RSS **4.112GiB**, RSS sau generation khoảng1.42GiB. Torch allocator process-peak VRAM **3.733GiB**, không bao gồm toàn bộ driver/context allocations. Đây là 2 synthetic demos, không SLA hoặc train-fit evidence. B0 warm CPU function khoảng0.026s/0.022s; không coi đây là so sánh cùng hardware/E2E path với GPU generation.

### Semantic acceptance vẫn chưa đạt

- Receipt tự điền `/items/0/unit="unit"`, không được quan sát trong OCR.
- Invoice tự điền đơn vị `"đơn vị"` và coi header `Mặt hàng / SL / Đơn giá / Thành tiền` là item thứ hai, kéo theo values lặp.
- B0 conservative trả null/empty vì demo dùng nhãn tiếng Anh như `merchant name`/`total amount`, khác rules tiếng Việt. Nhiều fields hơn không chứng minh Qwen chính xác hơn.
- Giữ nguyên raw/parsed predictions. `acceptance-verification.json` có **4 semantic findings** từ review observed OCR, không phải gold/training labels. Không sửa output để ép PASS, không tự tạo evidence/confidence.

**Kết luận:** model provisioning, CUDA load và native JSON/schema smoke đã được chứng minh; **business extraction quality chưa nghiệm thu**, cần source/evidence guard và xử lý header/unsupported values trước acceptance. Lead chưa sign off quality; M1.3/G0 train-step/checkpoint/reload vẫn NOT_RUN. Không fine-tune, deploy hoặc đổi B0 mặc định.

### Tests và provenance lần rerun

- M1.2 tests cuối: **74 passed**; full Windows AI gate **934 passed, 455 subtests, 1 allowed symlink skip**, 935 collected, exit0; JUnit/log tại ignored run folder.
- Linux focused suite sau API/memory fixes: **187 passed**. Sau prompt fix, lần định chạy Linux suite cuối **NOT_RUN** vì Docker endpoint `dockerDesktopLinuxEngine` mất; không claim 188 PASS. Native prompt-v2 run đã hoàn tất trước đó trong Docker, 4 outputs đã được validate lại độc lập trên host.
- Build/pip check/BF16/readonly mounts đã PASS trong Docker. Docker mất sau native run không làm mất model host; `model_provision --verify-only` trên host xác nhận VERIFIED lại.
- Model inventory/manifest, source hashes, Docker image ID `sha256:9d9909471112f6b0f5aec46229783b976cce2443cd3cdcb5870e2a2025249933`, full pip freeze, approval, observed OCR, configs, raw outputs, metrics, failures v2 và review findings nằm tại **`artifacts/evaluation/qwen3-m12-native-20261124/`**, được Git ignore.

Files source thay đổi trong native rerun: `infra/qwen-inference.Dockerfile`, `infra/README.md`, `ml/model_provision.py`, `ml/model_loading.py`, `ml/ocr_adapter.py`, hai unit-test files và tài liệu AI-2. Không đổi dependency pins hiện có, business contracts, OCR/Data/Backend source hoặc production lifecycle.
