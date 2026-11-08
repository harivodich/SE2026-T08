# Labels adapter — `vietdoc.field-labels.v1`

Owner: Data Engineer; consumer reviewer: AI2 (AI1 review data semantics).
Trạng thái: **adapter ready for consumer review**, chưa hoàn tất training handoff.
Đây là contract Python offline Data, không thay shared business JSON Schema.

## Input và cách dùng

API cũ `generator.integration.load_artifacts(root, manifest, full_set=False)` vẫn
yield `(sample, gold)`. Adapter mới dùng cùng boundary, yield
`(sample, gold, FieldLabels)`:

```python
from dataclasses import asdict
from pathlib import Path
from vietdoc.data.adapters.labels import VERSION, load_training_labels

root = Path.cwd()
manifest = root / 'tests/fixtures/d12/manifest.json'
for sample, gold, labels in load_training_labels(root, manifest):
    if labels.version != VERSION:
        raise ValueError('Unsupported label adapter version')
    by_pointer = {field.pointer: field for field in labels.fields}
    total = by_pointer['/total_amount']
    print(sample['sample_id'], asdict(total))
```

Input là renderer manifest D1.2 v1/v2, D2.1 v1 hoặc D2.2 v1 với schema ở
`root/specs/contracts/business.schema.json`. D1 asset paths tương đối với `root`;
D2 tương đối với thư mục manifest. Các file phải có sẵn; ví dụ không tải dữ liệu
hoặc chạy inference. Dùng Data dependencies đã khai báo trong `pyproject.toml`.
`full_set=True` giữ gate 20 IDs/type/layout/seed của D1.2; không áp dụng D2.

Output chỉ có scalar business leaves và line-item cells; `items` không là scalar.
Pointers là exact business JSON pointers như `/items/2/unit_price`, không nhận
aliases hoặc index ngoài row coverage. Values giữ `str | None`, money/quantity
không đổi sang float. `FieldLabels` và `FieldLabel` là frozen dataclasses;
`fields` là tuple sắp theo pointer (lexicographic, **không** là thứ tự hàng số).
Consumer cần đọc index trong pointer/gold nếu muốn giữ row order; không zip tuple
này với sequence OCR hoặc table rows. `sample`/`gold` giữ kiểu dict hiện tại.

Accessor in-memory `field_labels(gold, labels)` nhận labels map trực tiếp, không
nhận wrapper `{"labels": ...}`. Nó kiểm exact pointer coverage, shape label,
status/value/raw/reason consistency và string/null leaves. Nó **không** validate
business schema, manifest, hash, assets hoặc source semantics; caller phải có
validation boundary riêng. D1.1 content-only fixtures chỉ dùng cho unit oracle,
không được coi là renderer data đã audit chỉ vì accessor nhận được chúng.

Ví dụ rút gọn từ fictional `d11-invoice-02` (input đầy đủ phải có mọi leaf):

```json
{
  "gold": {
    "buyer_name": null,
    "total_amount": "180500",
    "items": [{}, {"quantity": null}, {"unit_price": null}]
  },
  "labels": {
    "/buyer_name": {"status": "absent", "raw": null, "reason": "Không in trường này."},
    "/total_amount": {"status": "present", "raw": "180.500 đ", "reason": null},
    "/items/1/quantity": {"status": "obscured", "raw": "?,?", "reason": "Không đọc chắc chắn."},
    "/items/2/unit_price": {"status": "unlabeled", "raw": null, "reason": "Chưa annotate."}
  }
}
```

`asdict(field_labels(gold, labels))` có cấu trúc sau (tuple thành array khi JSON
serialize); raw/reason không trở thành business value hoặc training target:

```json
{
  "version": "vietdoc.field-labels.v1",
  "fields": [
    {"pointer": "/buyer_name", "value": null, "status": "absent"},
    {"pointer": "/items/1/quantity", "value": null, "status": "obscured"},
    {"pointer": "/items/2/unit_price", "value": null, "status": "unlabeled"},
    {"pointer": "/total_amount", "value": "180500", "status": "present"}
  ]
}
```

## Validation và compatibility

`load_training_labels` chỉ yield sau khi toàn manifest đã validate. Nó dùng chính
labels object từ lần kiểm renderer, không mở lại labels sau validation hoặc suy
status từ `None`. Các gate path containment/hash, metadata/lineage, business
schema/type, pointer coverage, status counts, geometry/transcript/occurrences và
D2 variant semantics giữ nguyên. Lỗi có sample ID khi lỗi thuộc sample; lỗi
manifest/full-set có message ở dataset level. Không đổi format bytes, schema,
generator versions hoặc evaluator policy; vẫn reject unknown manifest versions.

Version `vietdoc.field-labels.v1` pin ý nghĩa value/pointer/status và output shape.
Consumer phải kiểm version được hỗ trợ; đổi ý nghĩa statuses/values hoặc shape
không tương thích cần version mới và consumer review. Version này không thay
dataset/manifest/schema pins; consumer vẫn phải ghi các pins/hash tương ứng.
Không cache kết quả như một validation receipt dùng lại cho file có thể thay đổi.

## Trách nhiệm consumer và acceptance còn chờ

| Status | Ý nghĩa dữ liệu | Trách nhiệm AI2 |
|---|---|---|
| `present` | Có business value dạng string | Dùng đúng normalization/target contract đã thống nhất |
| `absent` | Đã xác định trường không hiện diện, value null | Giữ riêng với unknown; trình bày cách supervise absence theo policy được review |
| `obscured` | Không có value truth đọc chắc chắn, value null | Không suy value từ raw/row arithmetic; không coi là labeled absence |
| `unlabeled` | Chưa annotate value, value null | Không dùng null làm gold absence hoặc tự fill từ prediction |

**PENDING — AI2:** nối adapter vào dataset/batch/collator/loss; đề xuất và review
mask/loss policy, không chỉ serialize gold bỏ statuses. Cần consumer tests chứng
minh ba cùng-null statuses giữ khác nhau qua actual batch, absent supervision
đúng policy và obscured/unlabeled không biến thành negative truth. AI2 ghi command,
sample/pointer mapping, adapter/dataset/model/config versions và evidence target,
mask, loss trên consumer thật. DE không triển khai thay training collator.

**PENDING — review/integration:** AI1/AI2 peer review, Lead acceptance, baseline
integration vào develop, hosted CI và post-merge consumer smoke. Chỉ claim training
handoff hoàn tất khi có consumer evidence. Không dùng fixture tests làm training
evidence, model quality hoặc calibrated confidence.

Validation chỉ chứng minh schema/metadata/assets/sidecar consistency theo boundary
hiện có; không chứng minh pixel/text alignment, historical render replay hoặc
annotation truth. Renderer D1 chỉ cho present/absent; D2.2 không sinh unlabeled.
Ba statuses cùng-null được test bằng tiny D1.1 content-only fixture; D2.2 file
adapter được kiểm bằng fresh bounded render. Không thêm public-source adapter,
handwriting, multipage, token alignment hoặc evidence geometry contract mới.
