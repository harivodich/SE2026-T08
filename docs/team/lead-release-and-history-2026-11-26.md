# Lead — CI release và bảo toàn lịch sử, 26/11/2026

## Phần đã triển khai

Source nền `develop` `277ce863c5c15c64aaaea2b7dbebe87e5afb7a7b`, tree `73acb1af0000b6c03cacdcb9c8623c4191111899`. Increment trên nhánh riêng, không sửa source dở ở checkout chính.

1. CI có bốn application jobs `backend`, `parity`, `application-artifact`, `e2e` nối vào release-readiness. Ba job đầu bắt buộc cả develop; E2E main dùng PostgreSQL riêng/native provider thật và kiểm thêm frozen V1 packet. Missing/fail/cancel/skip vẫn fail. Không tắt ruleset.
2. JAR của job test đi cùng strict JUnit/source/hash/migration receipt qua artifact của **cùng run**. Backend verifier từ chối test skip, thiếu mandatory class, report đổi hoặc JAR khác. Artifact smoke tải đúng JAR đã test, không rebuild. Docker demo riêng không được gọi là accepted model.
3. Parity Java/Python cùng16 positive/negative cases, so actual outcomes với oracle và corpus SHA. Cần reject đúng kiểu/version/ID/budget/hash/money/required/unknown fields; corpus không chứng minh mọi input khả dĩ.
4. Runner E2E reusable: Java JAR→PostgreSQL→OCR/B0 thật→review/approve/export. Hai type, PDF/PNG, stale save409, unapproved export409, anonymous401, export deterministic và isolation khỏi attempt đã bị sửa. Không dùng prediction làm gold; total sửa trong bước review được ghi rõ, không tính là accuracy model.
5. Runner có nhánh `--candidate-settings` để chạy **qwen-local có pins thật** qua existing candidate server. Thiếu config/snapshot/adapter pin hoặc extra command options bị reject; không fallback B0. Chưa chạy candidate này thành công chỉ từ việc có runner.

## Lịch sử đã phục hồi trong candidate local

`release/v1-preserved-history-20261126` tại `3485585520d686eb38bac386ce10f34c9e4d6070`:

- Từ116 lên171 reachable commits: thêm54 commit lịch sử đã có và một history-only merge rõ mục đích. Không tạo feature commits giả hoặc thay author/date/SHA gốc.
- Original heads **và merge commits** của25 PR đã merge đều reachable. PR vào feature branch chỉ nhận khi merge commit là ancestor của một primary PR đã được nhận.
- PR5/6 được chọn explicit historical-only: main cũ có merge/revert rồi quay về baseline. Giữ lịch sử đó không khôi phục code đã bỏ. PR đang mở, kể cả97, không đưa vào ancestry.
- Tree candidate bằng đúng develop nền; không có code diff. Không squash/rebase nhánh này khi nhận, vì sẽ mất ancestry vừa giữ.
- Có Git bundle hoàn chỉnh và diễn tập bare clone riêng: main mô phỏng171commit, tree đúng,50/50 original head+merge checks đạt. GitHub main/develop chưa bị đổi từ bước chuẩn bị này.

Script có thể tái dùng sau này với metadata GitHub mới:

```powershell
python scripts/preserve_pr_history.py --repo . --prs <pr-metadata.json> --base origin/develop --main origin/main --output <new-inventory.json>
```

Nếu có unresolved, phải làm rõ integration/revert trước. `--historical-pr` chỉ dành PR primary đã merge cần giữ như lịch sử đã bỏ, không dùng nhận PR chưa merge. `--prepare-branch release/<new-name>` tạo **ref mới**, không overwrite branch, checkout, sửa index, push hoặc merge main. Lấy đủ original PR heads/merge objects trước; thiếu object là fail, không gọi là mất commit trên server.

## Kiểm chứng và giới hạn

- Local parity Java16cases qua1JUnit test và Python outcomes: đạt.
- Java full build trên Windows:57tests, có1symlink test skip do quyền Windows. Không dùng bộ này làm strict release proof.
- Linux chạy nguyên test classes với Maven-resolved test dependencies:57/57Java,0skip; PostgreSQL job integration1/1. JAR cùng SHA `0de505a94b320e6f78f49da62ff1695a40e59485726b390c4010b4c070e04a36` qua receipt validation và actual smoke.
- Native B0 receipt/invoice actual end-to-end đã chạy trên nvit-train trong folder test riêng. Không chạy fine-tune mới và không nhận M0/M1 từ kết quả B0.
- Workflow qua actionlint/zizmor trên Linux; không có findings mới. Hosted CI trên head publish cuối vẫn bắt buộc trước merge.

Các số là phạm vi lượt kiểm tương ứng, không cộng unit/subtest/native cases thành model accuracy. Report đầy đủ, bundle/hash, snapshot diff và replay receipt ở gói evidence ngoài Git của Lead; không commit logs, weights, DB hoặc raw outputs.

## Phần thực sự còn cần đầu vào

| Đầu vào | Người cung cấp/nhận | Có thể làm ngay gì |
|---|---|---|
| Model/candidate đạt raw serving/schema và quality, GPU/profile thực, immutable pins | AI2 #57/#59; Lead chạy ghép | Runner/parity/artifact/native B0 đã có, không đợi để implement chúng |
| Metric oracle ACK, policy/targets frozen, final membership chưa lộ và final report | Data/AI1 theo packet; Lead #53/#54/#61 | Hoàn thiện oracles/runner trên train/dev/tiny fixtures ngay; không mở final hoặc bịa accepted packet |
| Actual candidate-model end-to-end với pins tương ứng | Lead sau AI2 handoff, Backend runner | Dùng `native_e2e --candidate-settings` cùng models release đã provision; không tải/thay weights âm thầm |
| Restore/rollback rehearsal của release đúng artifact/migration/data version | Lead sau artifact/candidate freeze; Backend cung cấp runner | PostgreSQL claim recovery đã test, nhưng không tự gọi nó là đủ mọi backup/restore case |
| Publication và hosted check của final head | User cho phép commit/push/PR riêng, Lead thực hiện khi có quyền | Source/tooling và local/Linux acceptance chuẩn bị được ngay; không giả hosted PASS |

Main gate sẽ báo `V1_NOT_READY` nếu chưa có accepted packet ở `docs/reviews/v1-acceptance/index.json`. Đây là thiếu actual acceptance input, khác với thiếu executable CI job trước đây. Code hoàn thành chưa tự đóng #95/#96 hay gọi main đã release: cần đúng publication/review/merge và postmerge smoke theo workflow.
