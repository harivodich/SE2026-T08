# Python AI/Data source

Đã có: compute contract adapter (`contracts/compute.py`), release manifest verifier (`ml/release_manifest.py`), normalizer `vi-VND.v2` (`pipeline/normalization.py`, policy cần Data/Lead review vì evaluator dùng chung), model output parser (`pipeline/extraction/output_parser.py`, no repair, strict shape), JSON logging, private FastAPI service (`entrypoints/api`, auth/limits/schema/hash/release/slot) và env report CLI. Chưa có preprocess/OCR/extraction/training, nên service trả `AI_NOT_READY` thay vì kết quả. Docker: [infra](../../infra/README.md). Python chỉ computation và offline Data/ML; Java quản lý business state.

Core package không cài dependencies. Chọn extra trong môi trường mới, từ repo root:

| Mục đích | Lệnh cài | Validator |
|---|---|---|
| Data renderer | `python -m pip install '.[data]'` | jsonschema 4.10.3; giữ Pillow 10.2.0 và fingerprint cũ |
| Compute contracts độc lập | `python -m pip install '.[contracts]'` | jsonschema 4.26.0 + referencing 0.37.0 |
| Serving và AI tests | `python -m pip install '.[serve,test]'` | cùng validator hiện đại |
| Training | `python -m pip install '.[train]'` | cùng validator hiện đại; torch theo wheel index phù hợp |

Data và AI dùng môi trường riêng; không cài gộp `data` với `contracts`/`serve`/`train` vì pins validator/Pillow khác nhau. `test` chỉ cung cấp test runner/client, cần đi cùng extra của suite. Validator pins được khai báo trực tiếp trong `contracts`/`serve`/`train` để Docker cài dependency layer khi chưa có application source.

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
