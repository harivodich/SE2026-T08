# BT3 - 23001863 - VT-029

Nhánh nộp: `feature/VT-029_search_contract` từ local `origin/develop`:
`e5326f34549a23570ecf935f469a1f0082ed8a11`. Người dùng xác nhận sử dụng workspace
SE2026-T08 thay URL SE2026.AI-02.1 trong đề. Không đổi remote.

Người dùng đã cấp quyền commit/push sau khi xem kết quả. [Link nhánh nộp](https://github.com/harivodich/SE2026-T08/tree/feature/VT-029_search_contract).
Implementation commit: `5405dbcd1c44d5c81e98c6c6f9e3b437c6f0b18d`.
Mutation local branch: `feature/VT-029_mutation_exception_swallow`,
commit `3f3d3e873a52b4e30e40f8f401142f035dee687a` (không push nhánh lỗi).
Không tạo PR/merge; nhóm chưa review. Báo cáo/reflection do AI hỗ trợ, chưa có xác nhận
review/cam kết cá nhân của sinh viên. Chi tiết ở evidence/git-history.json.

## Scope và contract

API slice: optional `q` tại GET `/api/v1/documents`, tìm filename literal, trim/case,
kết hợp type/status hiện có; giữ owner, Page/Document v1, keyset/cursor và order.
Không search OCR/payload, không có UI search controls. Xem
[`document-search.md`](../../specs/contracts/document-search.md) và
[`VT-029-plan.md`](VT-029-plan.md).

Production chỉ đổi DocumentController.java, DocumentService.java và openapi.json
(25 additions/2 deletions). Không đổi migration/schema DTO hoặc dependency runtime.

## Chạy tests

Cần JDK17+, Maven Wrapper tải dependency lần đầu; Node22 cho tests asset hiện có.
Python `jsonschema` có Draft202012Validator cho bước validate JSON. Môi trường này
dùng JDK có sẵn `/opt/pycharm/jbr` (25.0.4.1), Java compile target17; không cài service.

```bash
export JAVA_HOME=/opt/pycharm/jbr  # thay bằng JDK trên máy bạn
cd backend
bash mvnw -Dtest=DocumentSearchContractTest,DocumentSearchUnitTest test
cd ..
python3 scripts/vt029_contract.py
```

Frozen `backend/src/test/resources/vt029-v1-contract.json` là transitive closure
DocumentPage/ErrorEnvelope schemas từ baseline, không lấy schema mới làm oracle.
MockMvc xuất response thực tế ở `backend/target/vt029-contract/` rồi Python validate
theo Draft2020-12 + FormatChecker. Python hệ thống trong phiên có jsonschema4.10.3.

Regression và coverage:

```bash
cd backend
bash mvnw org.jacoco:jacoco-maven-plugin:0.8.14:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.14:report
cd src/test/js
node api.test.js
node app.test.js
node domain.test.js
```

Java regression: **40 tests, 0 failures/errors, 1 skipped** (load opt-in); 39 executed
pass. `DocumentService.list` search: **38/38 lines, 34/38 branches (89.5%)**.
4 nhánh thiếu là blank type (2 chỗ), blank status/cursor. HTML report ở
`backend/target/site/jacoco/`; counters gốc trong evidence/coverage-summary.json.
Không dùng coverage đơn độc để kết luận chất lượng. Browser E2E và PostgreSQL chưa chạy.

## Tải thực HTTP

```bash
cd backend
bash mvnw -Dvt029.load=true -Dtest=DocumentSearchLoadTest test
```

80 workers/barrier ×3 waves, warmup10; 240 rows synthetic trên Flyway/H2 memory.
Real Tomcat random port + CSRF/login/session, một session, q/type/first-page cố định.
Request duration gồm HTTP + parse/assert. Nearest-rank p95 của 240 successful tasks:
**351.622261 ms <=2500 ms**, **0 errors**. Không bật coverage agent ở load run.
Máy i5-11400H, 12 processors, khoảng15.3GiB host RAM; JDK25.0.4.1 Linux amd64.
Log/latencies gốc ở evidence/load.txt và load-result.json.

Không chứng minh 80 distinct users, PostgreSQL, mixed workload, sustained rate,
WAN/TLS, large DB, browser hoặc cold-start. Không assert p95 trong correctness test
để tránh timing flakes; test vẫn fail nếu response/status/ID/cursor sai.

## Mutation bắt buộc

```bash
# Từ root; đường dẫn Maven cache này là đường dẫn đã dùng trong phiên.
export MAVEN_USER_HOME=/tmp/vietdoc-vt029-maven
python3 scripts/vt029_experiment.py --maven-repo /tmp/vietdoc-vt029-m2 --output docs/reviews/vt029-evidence
```

Cache mặc định trên máy khác thường là `~/.m2/repository`; truyền đường dẫn thực tế
và bỏ MAVEN_USER_HOME nếu dùng default. Script chạy Maven offline, nên chạy test
thường để tải dependencies trước. Nó copy backend sang /tmp, thay controller bằng
catch RuntimeException trả empty Page, chạy TC12 và kiểm đúng assertion500/200.
Không có Git mutation/commit hay thay source chính. **KILLED**; hashes controller
trước/sau trùng. Bản đúng vẫn pass TC12 trong full regression.

Sau khi có quyền Git, đã thực hiện lại trên nhánh mutation local riêng (commit nêu
trên): `mutation-branch.txt` ghi 1 test/1 failure đúng500/200. Đã switch về nhánh
nộp, chạy lại TC12 pass (`restored-tc12.txt`). Nhánh nộp không chứa deliberate bug;
`mutation.patch` trong evidence cho phép replay mà không cần push nhánh lỗi.

## Evidence và báo cáo

`docs/reviews/vt029-evidence/`: RED hợp lệ12 tests/6 failures trước patch; RED đầu có
thêm assumption sai400/422; GREEN12, focused coverage14, final regression40; schema
fixture failure{}→[], schema pass; mutation kill; load; coverage; source manifest.
Các logs không là substitutes cho source/tests. Không thay tests chỉ để pass:
422 và metadata array lấy từ baseline contract/source; kỳ vọng search giữ nguyên.

Lệnh thực thi trong phiên thêm flags local (không yêu cầu đổi repo config):

```bash
export MAVEN_USER_HOME=/tmp/vietdoc-vt029-maven
bash backend/mvnw -o -B -ntp -f backend/pom.xml -Dmaven.repo.local=/tmp/vietdoc-vt029-m2 -Dtest=DocumentSearchContractTest,DocumentSearchUnitTest test
```

PDF: `output/pdf/BT3_23001863_VT-029.pdf`, 8 trang chính +2 trang phụ lục. Nguồn tái
tạo `scripts/vt029_report.py`; cần ReportLab/pypdf, font DejaVu hệ thống. Source text
đọc dễ hơn ở `VT-029-report.txt`. PDF ghi link branch đã published và implementation/
mutation commits; phần review/cam kết/reflection vẫn chờ sinh viên xác nhận.

## Checklist review nội dung đã thực hiện bởi agent

- Named parameter, literal wildcard, owner/cursor unchanged; invalid type giữ422.
- DTO/Page schemas đối chiếu baseline, fixture hợp FK; migration vẫn duy nhất V1.
- Không secrets/model/raw dataset/storage trong patch; không đụng files untracked
  có sẵn của người dùng; không cài service hoặc gọi paid API.
- Review độc lập của sinh viên/nhóm, browser, PostgreSQL và Unicode collation thực tế
  chưa chứng minh; không claim exactly-once/snapshot hoặc production capacity.
