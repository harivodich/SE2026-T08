# Bounded capacity benchmark

Chạy từ repository root trong Data environment đã pin (`Pillow==10.2.0`,
`jsonschema==4.10.3` và font đúng `d21.json`), không cài thêm dịch vụ/model:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m vietdoc.data.benchmark \
  --output outputs/capacity-small --rows 1 --base-limit 40 --repeats 1 --stage-timeout 300
```

Output phải chưa tồn tại. CLI không nhận existing dataset, final manifest, model
hoặc arbitrary generator config. D2.1 là synthetic integration/boundary QA, không
có split final. Không gọi D2.2 builder vì builder đó sinh cả family gán final.

Workload mỗi lượt: `4 * số row profiles + 4` attempted bases (hai loại, hai layout;
thêm hai missing-total và hai overflow probes). Rejections được giữ nguyên.
`--rows` unique trong 0–30, tối đa 9 profiles; `--base-limit` trong 1–40, mặc định
40, không có override vượt trần; `--repeats` 1–3; timeout mỗi process 1–600 giây.
Trần tổng là 120 attempts/3 lượt, 12 stage processes, 7200 giây child runtime;
không parallel. Limit theo attempts, không chỉ theo số sample accepted.

Mỗi pha process mới, timing gồm đúng operation sau imports/setup:

| Pha | Operation được đo |
|---|---|
| render | `d21.build`: values, source validation, render, PNG/PDF encode, ghi assets/report, kể cả rejection probes |
| validate | `d21.validate`: strict replay, render lại và so bytes/metadata/report |
| load | `extended.load_bundle`: asset reads/hash, consumer semantic gate, metadata/regions |
| evaluate | `extended.evaluate`: scalar/table/evidence core trên samples đã load, synthetic gold-copy payload, không OCR text |

Đây là bốn operation độc lập; validate có render lại, load có validation riêng,
không cộng chúng rồi gọi là exclusive production pipeline latency. Evaluate fixture
đo compute của scorer, không đánh giá model và không dùng predictions làm gold.
Không đo OCR edit-distance, inference, training, augmentation hoặc duplicate scan.

`benchmark.json` ghi config, attempted/accepted/rejected, versions/source hashes,
schema/vocabulary/font/environment, CPU/RAM/OS, wall/CPU seconds, process peak RSS,
disk logical/allocated bytes, manifest hash và failures. RSS là lifetime high-water
mark gồm imports/setup, không phải memory delta riêng pha; không đo GPU/cgroup
budget. Disk snapshot của stage chụp trước ghi result của chính stage; dataset disk
ghi riêng. OS cache không kiểm soát; không warmup. `run-NN/evaluate.json` giữ full
synthetic scorer report. Nếu worker fail/timeout, giữ partial output và summary
`status=failed`, dừng các pha sau. Không resume/ghi đè output cũ.

Pending AI2/Lead: hardware/model inference/train feasibility, pilot family/split
support, storage/time budget cuối và quyết định scale. Tối ưu chỉ làm task/PR riêng
sau baseline, không suy ra O(n²) từ giả thuyết. D2.2 cần benchmark riêng có cơ chế
chọn train/dev trước khi sinh values và giữ đúng contract validation.
