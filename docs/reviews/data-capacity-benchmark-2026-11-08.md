# Nhóm E — Bounded local capacity baseline, 2026-11-08

DE hoàn thành command và đo local. Hardware/model feasibility và budget cuối
vẫn chờ AI2/Lead; không đánh dấu các dependency này Done.

## Phạm vi và tái lập

Source E1: `d5eaa53` (`feat(data): add bounded dataset pipeline benchmarks`),
trên pipeline nền `fc2877e`. JSON evidence kèm source SHA-256 của Data/evaluator,
config hash, schema/vocabulary/font, environment và manifest hashes.
Không dùng số đo từ source khác làm baseline của commit này.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m vietdoc.data.benchmark \
  --output outputs/capacity-e-final-small-20261108 --rows 1 --repeats 2 --stage-timeout 300
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m vietdoc.data.benchmark \
  --output outputs/capacity-e-final-mixed-20261108 --rows 1 3 12 30 --repeats 2 --stage-timeout 300
```

Hai command chạy tuần tự, không benchmark/test song song. Các lần smoke ban đầu
ở `outputs/capacity-e-small-*`, `capacity-e-mixed-*` có contention hoặc source
đang thay đổi, bị loại khỏi bảng evidence cuối. OS cache và background load không
kiểm soát; chỉ hai observations mỗi cấu hình, không có percentile/SLA.

CPU Intel Core i5-11400H @2.70GHz, 12 logical CPUs/affinity12, RAM host
16,473,440,256 bytes (~15.34 GiB), x86_64 Linux/glibc2.39; Python3.12.3,
Pillow10.2.0/jsonschema4.10.3, DejaVuSans font pin. Visible cgroup v2 limits
không đọc được (`null`), RAM host không là budget được cấp cho model.
GPU/VRAM không được probe hoặc suy ra. Full hardware/environment nằm trong JSON.

D2.1 synthetic integration/boundary QA, hai type × hai layout; không có split
final. Workload gồm cả hai missing-total và hai overflow probes. Strict validation
render lại; consumer load cũng chạy semantic gate. Các pha không exclusive,
không cộng thành production end-to-end latency. Evaluate dùng synthetic gold-copy
payload để đo scorer scalar/table/evidence, không có OCR text hoặc model output.
Không có quality/calibration/accuracy claim.

## Số đo thật

Summary nguyên bản: [small](data-capacity-small-2026-11-08.json) và
[mixed](data-capacity-mixed-2026-11-08.json). Hai lượt của mỗi config có cùng
manifest SHA-256. Các JSON pin source benchmark khớp `d5eaa53`.

| Workload mỗi lượt | Attempts | Accepted / type | Rejected | Dataset logical / allocated bytes |
|---|---:|---|---:|---|
| rows `[1]` |8|6 =3 receipt +3 invoice|2|786,384 /884,736|
| rows `[1,3,12,30]` |20|18 =9 receipt +9 invoice|2|4,591,160 /4,837,376|

Mỗi workload chạy2 lượt; tổng56 attempted bases qua4 lượt, không phải56 base
độc lập. Missing-total là probe được giữ; hai rejected mỗi lượt là receipt/invoice
overflow, clipping bbox `[45,2602,677,2627]` vượt ảnh1500×2600. Không bỏ failures
để báo throughput. Mixed là nhiều row profiles của cùng bốn layout, không chứng
minh diversity của16/20 D2.2 families.

| Pha | Small wall giây, lượt1 /2 (median) | Mixed wall giây, lượt1 /2 (median) | Peak RSS MiB small /mixed, max2 lượt |
|---|---|---|---|
| render |3.426 /3.331 (3.379)|12.234 /15.320 (13.777)|87.54 /87.93|
| validate |3.962 /3.609 (3.785)|12.954 /15.032 (13.993)|102.38 /103.43|
| load |0.409 /0.464 (0.437)|1.340 /1.450 (1.395)|49.71 /52.14|
| evaluate |0.043 /0.038 (0.041)|5.860 /4.106 (4.983)|50.55 /56.27|

Full command wall tính từ summary timestamps: small19.114s/2 lượt,
mixed75.904s/2 lượt; gồm imports/setup và evaluate pre-load ngoài stage timers.
Đây vẫn là benchmark lặp nhiều operation, không latency request production.
CPU seconds có trong JSON. Peak RSS là process lifetime, gồm imports và pre-load;
không cộng các peak thành RAM pipeline hay coi nó là model budget. Dataset disk
chưa gồm các full scorer reports và stage summaries; không extrapolate thành toàn
bộ disk training/checkpoint. MiB =1,048,576 bytes.

Bottleneck đã đo: strict replay và build/render là hai operation chậm nhất trên
cả hai cấu hình; replay cố ý render lại để kiểm bytes. Mixed scorer core tăng lên
4.1–5.9s so với0.038–0.043s của small; workload đồng thời đổi số samples, row counts
và số repeated rows, nên chưa tách được nguyên nhân/thuật toán nào chi phối. Không
suy ra độ phức tạp O(n²), linear scaling, throughput D2.2 hoặc training feasibility
chỉ từ hai điểm này. Nếu cần profile row matching/encoding/duplicate scan, mở task
riêng và giữ baseline này làm mốc.

## Đề xuất capacity và phần còn chờ

| Hạng mục | Đề xuất / trạng thái | Owner và điều kiện |
|---|---|---|
| Local Data QA pilot có thể chạy ngay | Giữ batch mixed 20 attempts, không vượt40; repeat tối đa3, output mới; giữ rejection report | DE; chỉ integration/boundary QA đã đo, không training pilot |
| Pilot diversity để AI2/Lead xem xét | 16 clean bases: 12 train +4 dev, 1/base cho mỗi family train/dev hiện có; nếu giữ3 variants thì tối đa64 images | Proposed, chưa sinh trong task này. Cần train/dev-only generation trước values; không gọi full D2.2 builder mở family final |
| D2.2 capacity | Chưa đo augmentation/duplicate scan, không áp số D2.1 thành throughput D2.2 | DE follow-up riêng sau chọn population và review duplicate dispositions |
| Model feasibility | PENDING: pinned model/license, inference + train-step/checkpoint runtime, RAM/VRAM thực và failure accounting | AI2; xem issue51/56 và G0 Lead issue55; Data scorer RSS không thay được evidence này |
| Budget cuối / cho phép scale | PENDING: thời gian, disk reserve, hardware được cấp, family/support matrix và pilot size duyệt | Lead + AI2. Không tự tăng base-limit, mở final holdout hoặc approve capacity |
| Optimization | Chỉ đề xuất task/PR riêng sau baseline | Không thay implementation pipeline để làm benchmark đẹp hơn; không kết luận O(n²) |

16 bases đề xuất nhằm kiểm tra wiring/diversity sớm, không đủ chứng minh dev
calibration support hoặc final quality. Không tự hạ `dev_min_clean_per_type=100`
và không freeze protocol/manifest. Nếu budget chưa được chốt, chỉ lặp batch Data QA
đã đo; không mở rộng lên target3.000–6.000 clean bases.

## Verification trên source cuối

| Check thật | Kết quả | Giới hạn |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests/unit -p test_data_benchmark.py -v` |5/5 PASS|Bounds, worker guard, existing-output preservation, timeout accounting|
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_evaluation*.py' -v` |49/49 PASS,14.832s|Known-score/boundary/diagnostics tests, không model quality|
| Hai benchmark commands phía trên |4/4 trial complete,16/16 stages ok|Sequential local baseline, không controlled hardware performance lab|
| Reproducibility |Manifest hashes giống nhau giữa2 lượt mỗi config|Cùng source/environment/seed; không chứng minh cross-platform byte parity|
| Source pins |Summary source SHA-256 đối chiếu current source và commit E1|Không thay hosted CI hoặc reviewer acceptance|
| `git diff --check` |PASS|Kiểm diff của task, không full system test|

Không sửa generator/evaluator runtime, nên không chạy lại toàn bộ Java/DB/E2E
hoặc train/inference. Benchmark thật đã gọi build, strict replay và consumer semantic
validation. Không claim independent PDF pixel parser check/visual QA trong task E.
CI inventory dành cho test mới chưa được Backend xác nhận; focused tests chạy local.

## Handoff và merge dependency

PR mới chỉ thêm benchmark/tests/docs/evidence. Pipeline D2.1/D3.2 cần từ branch
`feature/duplicate_review_audit`; `origin/develop` local hiện chưa có modules này.
PR đặt base branch đó để reviewer thấy đúng diff E; Lead cần tích hợp pipeline
nền, rồi retarget/review PR vào `develop` theo Git Flow. Không tự merge parent
hoặc tự quyết các approval đang Proposed. Không có issue DE capacity riêng được
xác định; branch dùng `codex/data_capacity_benchmark`, không bịa `SE-<ISSUE>`.

Binary assets và full scorer fixture outputs ở ignored `outputs/`; chỉ summary
JSON an toàn và report này được commit. Không sửa schema, migrations, datasets
đã freeze, model settings hoặc CI của Backend. Hosted CI/consumer acceptance chưa
được xác nhận bởi local checks.
