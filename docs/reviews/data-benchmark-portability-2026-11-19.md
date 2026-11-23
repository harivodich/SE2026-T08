# #80 — B1/B2 benchmark portability, 19/11/2026

## Candidate và scope

PR [#80](https://github.com/harivodich/SE2026-T08/pull/80), branch
`feature/data_capacity_benchmark`, base PR vẫn `feature/duplicate_review_audit`.
Baseline trước fix: `48fa2977cc786d7c13d737ba6dca36621a985a23`.
Source/tests commit: `b75df3c72badd39e7f149848e8e324dc44bdfce0`.

Sửa B80-PORT trong cùng một increment chạy được; B2 regressions nằm cùng commit
B1 vì kiểm chính behavior sửa. Không thêm test-only commit rỗng. Không sync các
dependencies chưa merge, đổi base PR, sửa workflow/gate/matrix hoặc tự merge.
Giữ branch cũ local/remote, không force-push hoặc viết lại evidence lịch sử.

## Thay đổi behavior

- Bỏ module-scope `resource`; module import và pure workload guards portable.
- Runtime parent và worker yêu cầu Linux; font/hardware probes được cô lập trong
  `measurement_environment`, `resource` chỉ import trong worker sau platform gate.
- Giữ Linux RSS `ru_maxrss * 1024` bytes, process-lifetime scope, stage timers,
  workload/config/hash contract và output accounting. Không đo Windows RSS/RAM
  hoặc tạo unavailable values thành số đo giả.
- Năm guard cases cũ được giữ. Existing-output và timeout tests dùng environment
  fixture ở boundary không phải behavior đang kiểm; không phụ thuộc Linux font,
  `os.sysconf` hoặc hardware của runner Windows.
- Thêm fresh-process import khi resource unavailable, unsupported parent/worker/
  CLI, và worker failure sau completed render: giữ partial output/stage, stderr,
  failed status và không chạy load/evaluate.
- Synthetic stage numbers chỉ là unit-test fixtures trong temporary directories,
  không phải performance outputs hoặc evidence runtime.

Không đổi generator/evaluator source, schema, dataset split, metric policy,
base-limit/repeat/timeout bounds hoặc skip policy. P3 unexpected-interruption
observability vẫn là follow-up riêng, không âm thầm mở rộng scope.

## Focused local verification trước publication

Python 3.12.3/Linux, Pillow 10.2.0/jsonschema 4.10.3, font pin hiện có.
Prefix từ root: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`.

| Command sau prefix | Kết quả |
|---|---|
| `python3 -B -m unittest discover -s tests/unit -p test_data_benchmark.py -v` | 10 PASS, gồm nguyên 5 cases cũ |
| Cùng suite với `python3 -B -O` | 10 PASS; rerun, không cộng unique tests |
| `python3 -B -m unittest discover -s tests/unit -p 'test_evaluation*.py' -v` | 49 PASS |
| `git diff --check` | PASS |

Full local `python3 -B -m scripts.ci.checks tests data --separate-pdf` được chạy
sau bounded benchmark. Kết quả cuối của source/head được cập nhật trong PR #80;
focused snapshot này không chứng nhận full suite hoặc native Windows PASS.
Logs/full outputs ở ignored `artifacts/evaluation/data-benchmark-portability-20261119/`
và `outputs/capacity-portability-small-20261119/`, không commit raw assets.

## Fresh bounded Linux evidence

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.data.benchmark \
  --output outputs/capacity-portability-small-20261119 --rows 1 --repeats 1 --stage-timeout 300
```

Exit 0, 1 trial complete/4 stages ok, attempts 8 = accepted 6 + clipping rejections 2.
Một observation để kiểm đường measurement sau isolation, không median/SLA hoặc
benchmark so sánh cải thiện performance. Chạy tuần tự, trước full Data tests;
OS caches/background load không kiểm soát.

Summary byte-exact: [fresh small](data-capacity-portability-small-2026-11-19.json).
Kiểm đủ 31 source pins khớp committed source B1, config hash, manifest hash,
stage order/status và finite/nonnegative measurements. So với summary 08/11 chỉ
pin `data/benchmark.py` đổi; 30 Data/evaluator pins khác giữ nguyên.

| Pha | Wall seconds | Scope |
|---|---:|---|
| render | 2.579 | D2.1 build/encode/rejections |
| validate | 2.897 | Strict replay, có render lại |
| load | 0.332 | Consumer semantic gate và hashes |
| evaluate | 0.030 | Gold-copy synthetic scorer probe |

Peak RSS lớn nhất 102.16 MiB là process-lifetime high-water mark, không model
budget hoặc stage delta. Hardware/environment/source/config/asset provenance có
trong JSON. Không inference/train/GPU, D2.2 augmentation/duplicate-scan, chất lượng
model, calibration hoặc final holdout claim.

Hai summaries ngày 08/11 được giữ nguyên như historical baseline của source cũ;
không sửa hashes hoặc gán các số đo đó cho source B1 mới. Không cần chạy lại mixed
performance baseline để chứng minh platform guards; đây không là optimization.

## Windows/CI và integration acceptance

PR base hiện là parent feature, nên pull_request filter `[develop, main]` chưa
kích hoạt required VietDoc CI cho combined candidate. Các Web greens lịch sử
không thay Data matrix. Không đổi target sớm hoặc sửa owning CI để ép xanh.

Workflow hiện có `workflow_dispatch` cho phép chạy jobs trên source branch,
nhưng `scripts.ci.gate.target_branch` từ chối target ngoài develop/main. Nếu dùng
dispatch để kiểm Ubuntu/Windows matrix, đó chỉ là diagnostic portability evidence:
Data jobs có thể PASS trong khi `ci-gate` từ chối feature ref theo policy. Không
gọi run đó là required-gate PASS hoặc acceptance cuối của PR.

Native matrix results/run provenance được ghi trong PR #80 sau khi kiểm thực.
Acceptance cuối vẫn chờ #77/#78 merge, sync #80, retarget develop và required PR
CI trên combined candidate mới. Lead giữ quyền merge; AI2/Lead hardware/model/
pilot approvals không được đóng bởi benchmark Data này.
