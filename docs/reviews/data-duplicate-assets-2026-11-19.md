# D2 duplicate review — assets và queue, 19/11/2026

Increment chuẩn bị độc lập cho [#38 / D06](https://github.com/harivodich/SE2026-T08/issues/38).
Chưa đóng acceptance grouped split/pilot của issue.

Đã xác minh snapshot local `datasets/processed/d22-smoke-c` khớp manifest lịch sử:
80 samples, 20 clean bases, đủ **480/480 assets** với SHA-256 đúng. Trước đây
dispositions ghi assets chưa có trong workspace; observation này cập nhật khả năng
truy cập assets, không sửa lại lịch sử review hoặc kết luận ảnh đã được xem.

Packet an toàn trong Git:
[`d22-review-assets-2026-11-19.json`](../../datasets/manifests/d22-review-assets-2026-11-19.json).
Raw PNG/PDF/sidecars vẫn ở ignored storage; clone Git riêng chưa có assets.

## Bindings và kết quả đã kiểm

| Input/check | Kết quả |
|---|---|
| `d22-smoke-v01.json` SHA-256 | `eaabf08f5511de0db7bfdf9b7f087716cd0acf197bb00bca9fcb34341f8314db` |
| `d22-report-v01.json` SHA-256 | `5173053cfb5197fe4e6642ed1a903a96b5f41f7ffcf0531c4029ffabc8af0d1e` |
| Local `manifest.json` / referenced report | Byte hashes khớp hai inputs trên |
| Asset paths | 480 paths duy nhất, resolve trong snapshot root, files tồn tại |
| Asset inventory | Mỗi sample đủ png/pdf/gold.json/txt/regions.json/labels.json |
| Asset bytes | 480 hashes khớp manifest; không chỉ kiểm file names |
| `splits.duplicate_report(samples)` | Khớp toàn bộ historical `report.leakage` |
| Queue | 81 unique candidate IDs; 43 cross-split, 38 same-split |
| Existing #78 dispositions tại `fc2877e` | Cùng đúng 81 IDs, toàn bộ vẫn pending; không ghi đè file review |
| Split images hiện có | train 48, dev 16, final 16; `final_frozen=false` |

Đây là historical synthetic integration smoke, không là untouched holdout.
Hash verification không chứng minh annotation/pixel correctness, strict render
replay, independence, leakage-cleared hoặc pilot readiness. Không chạy inference,
training, sinh thêm dữ liệu, đổi grouping/splits hoặc hạ dev support.

## Lấy đúng assets trước review

Dùng snapshot trên hoặc nhận bản copy qua storage được team cho phép. Không
regenerate bằng renderer hiện tại rồi coi là historical bytes; nếu hashes khác,
dừng review và lấy đúng snapshot hoặc đề xuất version mới. Không commit raw assets
hoặc tự upload chúng lên GitHub. Trong snapshot, asset paths được resolve tương
đối với thư mục chứa local `manifest.json`; không resolve tương đối với bản
metadata-only ở `datasets/manifests/`.

Chạy từ repository root; Python standard library và source Data hiện có là đủ:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B - <<'PY'
from collections import Counter
from pathlib import Path
from vietdoc.data.manifest import ASSETS, asset_path, read_json, require, sha
from vietdoc.data.splits import digest, duplicate_report

root = Path('datasets/processed/d22-smoke-c')
packet = read_json('datasets/manifests/d22-review-assets-2026-11-19.json')
inputs = {}
for key in ('manifest', 'report'):
    ref = packet[key]
    path = Path('datasets/manifests') / ref['name']
    require(sha(path) == ref['sha256'], key + ' binding drift')
    inputs[key] = read_json(path)
m, r = inputs['manifest'], inputs['report']
require(sha(root / 'manifest.json') == packet['manifest']['sha256'], 'snapshot manifest drift')
require(m['report']['sha256'] == packet['report']['sha256'], 'manifest/report drift')
require(sha(asset_path(root, m['report']['path'])) == packet['report']['sha256'], 'snapshot report drift')
require(duplicate_report(m['samples']) == r['leakage'], 'screening drift')
source = packet['screening_source']
require(sha(source['path']) == source['sha256'], 'screening source drift')
seen = set()
for sample in m['samples']:
    require(set(sample['assets']) == set(ASSETS), 'asset inventory drift')
    for asset in sample['assets'].values():
        require(asset['path'] not in seen, 'reused asset path')
        seen.add(asset['path'])
        require(sha(asset_path(root, asset['path'])) == asset['sha256'], 'asset hash drift')
expected = sorted(r['leakage']['ambiguous'], key=lambda p: (not p['cross_split'], digest(sorted(p['base_ids']))))
require(len(packet['queue']) == len(expected) == 81, 'queue coverage drift')
counts = Counter()
for rank, (entry, pair) in enumerate(zip(packet['queue'], expected), 1):
    kind = 'cross-split' if pair['cross_split'] else 'same-split'
    counts[kind] += 1
    require(entry == dict(rank=rank, batch=f'{kind}-{(counts[kind]-1)//10+1:02d}',
                         candidate_id='pair-' + digest(sorted(pair['base_ids'])), **pair), 'queue drift')
clean = sorted((s for s in m['samples'] if s['quality'] == 'clean'), key=lambda s: s['base_id'])
keys = ('base_id', 'sample_id', 'family_id', 'source_group', 'document_type', 'split')
require(packet['bases'] == [{k:s[k] for k in keys} for s in clean], 'base lookup drift')
require((len(seen), len(m['samples']), len(clean), counts['cross-split']) == (480, 80, 20, 43), 'snapshot counts drift')
print('480 asset hashes PASS; 20 bases; 81 candidates; 43 cross-split; no visual decisions')
PY
```

Observation ngày 19/11/2026: command trên exit 0 trên Python 3.12.3/Linux.
Không thêm unit tests cho packet metadata; verification kiểm trực tiếp bytes,
candidate recomputation và queue bindings. Không claim hosted CI từ command local.

## Chia nhỏ review và commit tiếp theo

Queue sắp cross-split trước, rồi theo stable candidate ID; rank không là mức độ
chắc chắn duplicate. Batches tối đa 10 pairs để reviewer kiểm từng phần:

| Phần | Pairs | Công việc / commit đề xuất | Dependency |
|---|---:|---|---|
| D1a | 81 | `docs(data): pin duplicate review asset queue` — packet/hash availability | DE tự làm, không dispositions |
| D1b | 81 | `docs(data): document duplicate review handoff` — runbook/evidence protocol | DE tự làm, không approval |
| D2a | 10 × 4 + 3 | `data: record cross-split review batch 01` … `05` | DE xem ảnh/nội dung/lineage; AI-1/AI-2 review; chưa đổi split |
| D2b | 10 × 3 + 8 | `data: record same-split review batch 01` … `04` | Cùng evidence; ambiguous phải giữ unresolved |
| D2c | Theo findings | Dataset version/grouping/split proposal riêng nếu có leakage thật | Lead duyệt trước implementation thay dataset |
| E1 | Proposal | Chốt pilot train/dev-only và resource/support với AI-2/Lead | Chưa sinh pilot hoặc mở final |

D1a/D1b chỉ ghi prep evidence và có thể nhận riêng. D2 dispositions tiếp tục dùng
tooling của #78 sau khi hội tụ #77 → #78 vào develop; không copy implementation
của #78 sang increment này. Không merge #80 vào feature parent để vượt dependency.
Các commits D2 ở bảng là kế hoạch, chưa được tạo.

## Evidence cho từng pair

1. Từ queue lấy `candidate_id` và hai `base_ids`; lookup `bases` lấy clean
   `sample_id`, rồi lấy asset paths/hash từ pinned manifest. Xem cả hai clean PNG
   ở độ phân giải đọc được, đối chiếu gold/transcript/labels/regions và source,
   family, base, assignment lineage. Variants cùng base không phải diversity mới.
2. Ghi candidate ID, input hashes, reviewer identity, image/content/lineage đã xem,
   ví dụ vị trí/nội dung/bố cục giống và khác, lý do disposition. Nếu xem thêm
   variants, ghi sample IDs và hashes tương ứng. Unequal hashes hoặc dHash thấp
   không đủ kết luận distinct/duplicate; không lấy predictions làm gold.
3. Chỉ chuyển khỏi `pending` khi đủ ba nhóm evidence. Chưa đủ thì giữ pending;
   không chắc sau kiểm thì `ambiguous`, vẫn unresolved. AI attribution không
   thay human sign-off. Việc DE chuẩn bị packet này không tạo visual evidence.
4. Commit từng batch chỉ gồm dispositions và safe review notes; chạy audit CLI
   và duplicate-review regressions của #78, báo counts remaining/cross-split sau
   từng batch. `review_complete` chỉ là coverage, không tự là Lead approval hoặc
   clearance khi còn ambiguous. Không đổi thresholds để hết candidates.
5. Findings duplicate/cross-split chuyển AI-1/AI-2 và Lead quyết định grouping,
   version/split và rerun audit. Không âm thầm sửa historical manifests hay tự
   gán all-distinct. Lead quyết định pilot/freeze; AI-2 sở hữu model feasibility.

Giữ toàn bộ branch local/remote sau merge theo yêu cầu người dùng. Không tự merge,
delete branch, force-push hoặc thay CI/settings. Required checks của #77/#78/#80
vẫn phải gắn đúng final candidate; packet này không đóng các dependencies đó.
