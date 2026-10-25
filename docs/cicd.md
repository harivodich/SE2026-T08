# CI/CD VietDoc

## Phạm vi đang chạy

Workflow `VietDoc CI` kiểm increment Data/contracts có thật trên branch CI. Nó không chứng minh backend, Python serving, PostgreSQL hoặc luồng ứng dụng đã hoàn tất. Deploy chưa được cấu hình vì chưa có server/registry/credentials được chỉ định.

```text
PR → develop: workflow + schemas/gate tests + Data matrix + Data wheel → ci-gate
PR → main:    các kiểm tra trên + application release checks             → ci-gate
```

PR vào `develop`/`main`, push lên hai branch và manual dispatch đều được xử lý. Không paths filter, nên docs-only PR vẫn có required check. Push lên feature branch không chạy thêm một bản trùng với PR. Manual dispatch chỉ chẩn đoán, không thay check PR. Workflow dispatch cần workflow trên default branch mới được GitHub cho gọi; không tự merge lên main để kích hoạt nút này.

## Jobs và environments

| Job ID | Check hiển thị | Nội dung |
|---|---|---|
| workflow | workflow-validation | actionlint 1.7.12 và zizmor 1.31.1, tải binary upstream và kiểm SHA-256 trước khi chạy |
| contracts | schemas-and-gate-tests | 7 schemas Draft 2020-12, fixtures positive/negative, registry local không tải refs; regression gate |
| data | data-OS-pyVERSION | Ubuntu 24.04/Windows 2025 × Python 3.11/3.12, fresh Data install, tests và 20 samples |
| package | data-package-smoke | Build wheel, kiểm fictional dictionary được package, cài wheel ngoài checkout, sinh 4 samples, ghi hash/source SHA |
| release-readiness | release-readiness | Main candidate phải có các application jobs thực sự thành công |
| ci-gate | ci-gate | Tổng hợp required jobs; missing/failure/cancelled/skipped của job bắt buộc đều fail |

Không có runtime Java/AI job giả. `release-readiness` hiện báo thiếu `backend`, `postgres`, `ai`, `parity`, `e2e`, `application-artifact` khi chạy với target main. Thêm các file Java/model không tự làm gate xanh; phải nối executable jobs tương ứng vào `needs` và có kết quả success.

Trên develop, chỉ `release-readiness` được skip có chủ đích vì chưa phải main candidate; chính trạng thái skip này cũng được aggregator kiểm. Trên main nó bắt buộc success. Không thay `always()` ở aggregator bằng điều kiện mặc định khiến prerequisite failure làm aggregator skip và bị GitHub coi là đạt.

Data dùng pins Pillow 10.2.0/jsonschema 4.10.3 trong `pyproject.toml`; `.github/ci-constraints.txt` pin transitive/build tools cho CI. Schema/gate tests dùng environment riêng với `.github/contract-requirements.txt`, jsonschema 4.26.0 + referencing local registry. Validator 4.10.3 đã tái hiện lỗi nested URN `$ref` giữa các shared schemas; không đổi renderer dependency để xử lý lỗi đó.

Portable Data tests mặc định skip đúng một canonical-byte test. Runner fail khi thiếu test file, mỗi module discover rỗng, tổng inventory nhỏ hơn baseline, hoặc có skip khác. Schema/gate tests không được skip. Mỗi suite ghi count/version/skip reason vào job summary.

Canonical bytes cần đúng fingerprint ở `tests/fixtures/d12/canonical-environment.json`, kể cả native libraries và font hash. OS/Python version giống nhau chưa đủ. Khi có canonical environment đã xác minh, bật `VIETDOC_CANONICAL_BYTES=1`; mismatch phải fail. Portable green không là canonical proof.

## Chạy local

Từ repo root, với Python 3.11/3.12. Tách hai venv, không cài schema requirements lên venv Data:

```sh
python -m venv .venv
.venv/bin/python -m pip install -c .github/ci-constraints.txt setuptools wheel
.venv/bin/python -m pip install --no-build-isolation -c .github/ci-constraints.txt '.[data]'
.venv/bin/python -m scripts.ci.checks tests data
.venv/bin/python -m scripts.ci.checks integration
.venv/bin/python -m scripts.ci.checks package
.venv/bin/python -m scripts.ci.lint

python -m venv /tmp/vietdoc-contract-env
/tmp/vietdoc-contract-env/bin/python -m pip install -r .github/contract-requirements.txt
/tmp/vietdoc-contract-env/bin/python -m scripts.ci.checks tests contracts
/tmp/vietdoc-contract-env/bin/python -m scripts.ci.checks tests ci
```

Chọn directory venv mới, không ghi đè môi trường đang dùng. Windows thay `bin/python` bằng `Scripts/python.exe`; đặt venv schema vào một directory local khác. Font được resolver tìm từ DejaVu/Arial đã có; có thể đặt `VIETDOC_DATA_FONT` là path font có license phù hợp. Không có font thì fail rõ.

Integration tạo output/manifest trong temporary directory dưới `datasets/processed`, verify cùng manifest đủ 20 IDs/10 receipt/10 invoice rồi cleanup directory của chính lần chạy. Không đọc ignored output cũ và không sửa tracked reference manifest. `dist/` chứa đúng một wheel; dùng clean checkout/directory build để tránh nhiều versions. Artifact upload chỉ gồm `dist/*.whl` và `dist/data-package.json`, retention 7 ngày; không là GitHub Release hay bản deploy.

## Required checks và quyền Lead

Giữ hai ruleset hiện có: owner-only update `25789985` và PR review/safety `25790016`. Chỉ `harivodich` có PR-only bypass để Lead tự quyết định merge, kể cả PR do Lead tạo. Teammates có thể comment/review và push feature branches nhưng không update/merge main/develop.

Required CI phải ở **ruleset riêng**, target chính xác `refs/heads/main` và `refs/heads/develop`, không actor nào bypass. Required context là `ci-gate`, expected source là GitHub Actions app ID đọc từ successful check-run thật. Dùng strict/up-to-date check khi bật để candidate phải được kiểm với base hiện hành. Không thêm CI rule vào ruleset Lead bypass vì như vậy tick bypass approval có thể bỏ cả test.

Trình tự bootstrap:

1. Push branch CI và mở PR develop. Xác minh hosted checks trên head/test-merge SHA của PR; không dùng manual run hoặc green SHA cũ.
2. Chạy controlled probes: prerequisite test fail phải làm ci-gate fail; main candidate chưa có application checks phải fail; docs-only update vẫn tạo check.
3. Lead merge PR CI vào develop. Không tự merge trong task triển khai CI này.
4. Xác minh workflow tồn tại trên develop và có successful check `ci-gate`; lúc đó mới bật ruleset required CI riêng. Nếu CI PR chưa merge, chuẩn bị settings/payload và báo rõ trạng thái chưa enforce; không khóa các PR cũ bằng check chưa được tích hợp.
5. Các feature branches cũ phải merge/update develop đã có workflow rồi chạy lại CI; không force-push hoặc tắt gate để vượt missing checks. Main release candidate phải chứa workflow và có release evidence.

Lead không cần teammate approve, nhưng CI gate vẫn bắt buộc với Lead. Nếu muốn emergency bypass CI sau này, đó là thay đổi policy riêng, không dùng chung bypass review hiện tại.

Khi cần khôi phục setting CI gây sự cố: chỉ Lead được disable đúng ruleset CI mới sau khi đọc lại ID/cấu hình và xác định nguyên nhân. Giữ nguyên hai ruleset owner/review. Ghi lý do/ảnh hưởng và bật lại sau khi check sửa đã thành công. Không tự disable trong workflow, không mở quyền cho write role.

## Security và tài nguyên

- PR jobs chỉ `contents: read`, checkout không lưu credential, không dùng secrets, `pull_request_target` hoặc privileged `workflow_run`.
- Actions pin full SHA; validator release binaries có hash pin. Dependency/tool updates qua PR và chạy lại checks.
- Không cache environment chung Data/AI; hiện chưa dùng cache để tránh reuse artifact không phù hợp.
- Jobs có timeout; CI runs cũ cùng event/PR bị cancel. Cancel không là success; cancelled/missing required checks vẫn chặn merge.
- JSON needs qua environment variable, đọc GitHub event file để xác định base main/develop; không nội suy title/body vào shell, không dùng workflow input để khai đã qua release.
- Không upload source workspace, datasets thật, weights, runtime storage, token hoặc browser state. Evidence chỉ fixtures synthetic/check counts và Data wheel.

## Release, delivery và deploy

Increment này chỉ tạo tested **Data package artifact**, không có app release artifact hoặc deploy. Không có credential hay secret nào cần thêm cho CI hiện tại.

Trước release ứng dụng, cần executable backend/DB/AI/parity/E2E/artifact jobs. Khi nối được, PR develop → main phải qua các gate đó. Build artifact cuối ở đúng main SHA, smoke chính artifact ấy, ghi checksum/image digest/schema/model release IDs. Publish/promote cùng artifact đã kiểm, không rebuild khác rồi gắn evidence cũ.

Tag theo `BUILD_VietDoc_<version>` / `RELEASE_VietDoc_<version>`; không reuse/di chuyển tag. Task này chưa tạo tag, GitHub Release, registry publish hoặc deployment.

Khi có đích deploy, Lead cung cấp tên host/environment, registry, phương thức auth và vị trí lưu artifact; không dán secrets vào chat. Đặt credential giá trị trong GitHub environment secrets theo tên config đã chọn, tối thiểu quyền. Chưa có đích deploy nên không đoán tên secret hoặc tạo workflow deployment TODO.

Production environment chỉ chọn reviewer `harivodich`, giới hạn main/release tag đã kiểm, không bật Prevent self-review làm Lead tự khóa khi kích hoạt workflow. Kiểm plan hỗ trợ trước khi cấu hình. Deploy jobs serialize theo environment, không tự cancel deploy đang thay đổi DB/app. Publish/deploy chỉ từ trusted event và candidate đã qua gate, không từ PR.

Runbook deploy cần: artifact digest/source SHA → backup/restore evidence → forward Flyway migration → start → readiness/health → smoke upload/review/approve/export → ghi kết quả. Rollback app về artifact đã phát hành trước; migration DB cần kế hoạch tương thích/forward repair đã kiểm, không rollback destructive tự động.

## Việc nối tiếp theo role

| Owner | Đầu ra cần thêm |
|---|---|
| Backend | Java tests/package/JAR/assets/Docker job; PostgreSQL/Flyway claim/CAS/race; browser workflow; release artifact; cùng Lead chọn đích deploy |
| Data | Duy trì test inventory, manifests/labels và isolated render dependencies; cung cấp canonical environment có fingerprint nếu cần byte proof |
| AI-1 | Preprocess/geometry/OCR tests và provider evidence không tải model trong default CI |
| AI-2 | Python service/unit/contract/lifecycle tests, environment riêng; Java/Python parity và actual-provider smoke có model version/hardware |
| Lead | Review/merge workflow và role PRs; bật required CI khi bootstrap đủ; duyệt scope release, environment và deploy |

Không cần thay đổi topology/Kubernetes/self-hosted runner để hoàn tất foundation này. Khi module chưa được merge, trạng thái của module là chưa tích hợp, không là skipped-but-release-complete.

## Nguồn chính thức

[GitHub required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks) giải thích latest SHA, workflow path filtering và việc skipped check không chặn merge. [GitHub Actions security](https://docs.github.com/en/actions/reference/security/secure-use) là nguồn về token scope/action pinning. [Deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) mô tả reviewer/self-review và branch restrictions. [jsonschema referencing](https://python-jsonschema.readthedocs.io/en/stable/referencing/) mô tả registry in-memory dùng trong schema suite.
