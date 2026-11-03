# VT-030 – chạy lại bài cá nhân 23001870

Increment bổ sung HTTP `Location` cho async job monitor; giữ nguyên response body, worker, DB schema và UI. Tests xác minh các invariant retry có sẵn. Không merge nhánh bài tập trước review nhóm.

- Baseline: `729be6fe493dc00e1d7cb87e7db94b94c79a0816` (`develop`).
- Test-first: `2d34f4c10cc4b8a692982be93ac0b4d6c6643d28` (21 tests, 1 failure Location sau khi sửa oracle cache).
- Patch/boundaries: `e3b3850000fa0a8f8f499bbc7ae7a88f06fdbc3d`.
- Review-strengthening: `a1055c300f2321ba64f0f46582348f63b258a542` (TC21 kiểm same id/reserved run và count sau replay; mutation parser dùng fresh JUnit XML).
- [Nhánh nộp](https://github.com/harivodich/SE2026-T08/tree/codex/bt3-vt030-async-idempotency).
- [Spec/plan](SPEC.md), [test matrix](test-matrix.md), [báo cáo](report.md), [evidence](evidence/).

## 1 - Prerequisites và focused tests

JDK 17; Maven Wrapper có sẵn. Lần đầu cần mạng để lấy Maven/dependencies từ repository đã cấu hình, không cần Python model, GPU hoặc PostgreSQL cho các case H2 này. Từ repo root:

```powershell
cd backend
.\mvnw.cmd '-Dtest=Vt030AsyncContractTest,Vt030MappingTest' test
.\mvnw.cmd '-Dtest=Vt030LoadTest' test
.\mvnw.cmd '-Dtest=*Test' package
```

POSIX thay `.\mvnw.cmd` bằng `./mvnw`. Focused functional: 25 invocations (19 API/service + 6 unit); load: 2; cả backend: 50 (27 mới VT-030, 23 baseline). Không cộng chạy lặp thành coverage mới. Reports ở `backend/target/surefire-reports`.

Lệnh focused Windows đầu tiên đã được chạy đúng argv 25/25 pass (`windows-wrapper.*`); môi trường kiểm chứng đặt JAVA_HOME và Maven cache qua MAVEN_USER_HOME/MAVEN_OPTS, giá trị trong JSON. Tool mutation Windows cũng được chạy (`windows-mutation.*`). Các command coverage/load/build còn lại là hướng dẫn portable tương đương; exact argv lịch sử (Git Bash, settings/cache riêng) ở metadata, không nhận là đã chạy mọi biến thể shell.

Muốn tái hiện red, checkout **một worktree/clone sạch riêng** tại test-first commit rồi chạy focused command: 21 tests, 1 assertion fail vì thiếu `Location`. Trở lại nhánh nộp: 25 pass do có thêm boundary/quota cases. Không checkout đè working tree đang có sửa.

## 2 - Coverage

Working directory `backend`, JaCoCo pin 0.8.14; không cần sửa POM:

```powershell
.\mvnw.cmd '-Dtest=*Test' '-Djacoco.append=false' org.jacoco:jacoco-maven-plugin:0.8.14:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.14:report
```

Mở `target/site/jacoco/index.html`; XML là `target/site/jacoco/jacoco.xml`. Snapshots ở `evidence/jacoco.xml` (đầu) và `final-jacoco.xml` (sau review), counters giống nhau; `coverage-summary.json` tổng hợp các counters đó. Line/branch 80,64%/63,38% thuộc full backend suite, không phải chỉ test mới; không nhận tỷ lệ này là bằng chứng đủ mọi behavior. Method không có branch counter ghi N/A, không ghi 100% branch.

## 3 - Mutation có thể khôi phục

Chỉ chạy trong checkout tạm sạch, không chạy đồng thời với tests khác vì script sửa mapper tạm thời. Script dùng argv, không shell interpolation, restore bytes trong `finally`. Từ root, Python 3:

```powershell
python scripts/vt030_mutation.py -- cmd /c mvnw.cmd -B
```

POSIX: `python scripts/vt030_mutation.py -- ./mvnw -B` (script đổi cwd sang backend). Output mặc định `backend/target/vt030-mutation`; script exit 0 nghĩa là **test subprocess fail vì mutant đúng oracle và source đã restore**, không phải mutant pass. Xem `mutation.json` trước khi kết luận. Trong evidence đã nộp có một experiment nhánh tạm riêng: `09cd8a2169eade641bca2a4a426411736d37c029`; mutant không thuộc lịch sử nhánh nộp. `mutation-branch.patch` tái hiện đúng thay đổi mà không cần push nhánh lỗi.

## 4 - Flaky và tải

Working directory `backend`:

```powershell
.\mvnw.cmd '-Dtest=Vt030AsyncContractTest,Vt030MappingTest' '-Dsurefire.runOrder=random' '-Dsurefire.runOrder.random.seed=17' '-Djunit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random' '-Djunit.jupiter.execution.order.random.seed=17' test
```

Đổi cả hai seed thành 83 cho lần khác. Evidence thực tế trước đó đặt JUnit seeds 17/83; Surefire tự sinh class-order seed, giá trị cụ thể có trong từng raw log. Sau review còn có `final-order-seed17/83` kiểm assertions cuối. `order-comparison.json` đối chiếu thứ tự testcase ghi trong XML, không chỉ dựa config. Command trên pin cả class-order để chạy mới dễ lặp lại, không được nhận là chính command lịch sử.

Load test có 200 ready threads, release chung, pool DB 10; đếm mọi outcome kể cả exception/timeout, nearest-rank p95 và peak inflight. Snapshot JSON đầu ra ở `target/vt030-results/*.json`: sao chép trước lần chạy mới. Hai runs chính `load-repeat1/2` đều đủ200/0lỗi/peak200, không chạy song song load với load khác. `load-instrumented-*` là run phụ khác warm-up, giữ riêng. H2/MockMvc seeded sessions/docs, không có TCP/login/upload/inference trong timer; p95 chỉ admission. Muốn đo deployment thật phải dùng PostgreSQL + TCP + actual provider riêng.

## 5 - Browser chức năng

Cần Chrome và module Playwright đã cài (không tự tải trình duyệt). Build JAR bằng lệnh package bên trên. Trong terminal riêng tại `backend`, chạy local demo trên cổng trống; worker tắt để quan sát QUEUED, storage riêng có thể xóa sau test:

```powershell
java -jar target/vietdoc-backend-1.0.0.jar --spring.profiles.active=demo --server.port=18830 --server.address=127.0.0.1 '--spring.datasource.url=jdbc:h2:mem:vt030browser;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DEFAULT_NULL_ORDERING=HIGH' --vietdoc.storage=./target/vt030-browser-storage --vietdoc.worker-enabled=false
```

Ở terminal khác tại repo root (thay module path nếu Playwright không nằm trong local node_modules):

```powershell
$env:CHROME_PATH='C:/Program Files/Google/Chrome/Application/chrome.exe'
$env:PLAYWRIGHT_MODULE='playwright'
New-Item -ItemType Directory -Force backend/target/vt030-browser | Out-Null
node scripts/vt030_browser.cjs http://127.0.0.1:18830 backend/target/vt030-browser
```

Chờ `/health/ready` trả200 trước browser. Dừng JVM bằng Ctrl+C sau test. Script login demo, upload synthetic sample, observe monitor/UI polling, replay original key, cancel và observe UI. Demo credentials là fixture công khai, chỉ chạy loopback; không dùng production. Không chứng minh automatic retry của UI hay OCR đã hoàn tất.

## 6 - Evidence và giới hạn

Các JSON `red-reviewed`, `green`, `full-coverage`, `order-seed*`, `load-repeat*` lưu command/timestamp/exit code. `curation.json` đánh dấu raw giữ ngoài repo, redaction token tổng hợp và loại XML stale. `manifest.json` là SHA-256 tập file cuối. Không giữ dataset, model binaries, real documents/PII hoặc credentials trong nhánh.

Residual work: PostgreSQL multi-runner/crash-after-effect, UI lost-response key reuse, model/provider E2E, TCP production load; notification delivery khi module có thật. Không nhận nhóm đã review, CI hosted đã pass hoặc code đã merge chỉ từ local tests.
