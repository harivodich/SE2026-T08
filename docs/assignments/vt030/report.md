# BT cá nhân 3 – AI-02 – VT-030
Nguyễn Hoàng Hải – MSSV 23001870 – Vai trò: Nhóm trưởng.
Team: SE2026-T08. Đề tài: Document Intelligence cho biểu mẫu tiếng Việt.
Repository: [harivodich/SE2026-T08](https://github.com/harivodich/SE2026-T08).
Baseline develop: 729be6fe493dc00e1d7cb87e7db94b94c79a0816.
Branch: [feature/bt3-vt030-async-idempotency](https://github.com/harivodich/SE2026-T08/tree/feature/bt3-vt030-async-idempotency).
Source/tests sau review: a1055c300f2321ba64f0f46582348f63b258a542.
Ngày kiểm chứng: 04/11/2026 (UTC+7). URL SE2026.AI-02.1 trong đề là tên repo trước khi đổi tên.
Tôi chịu trách nhiệm về toàn bộ code, test và nội dung bài làm; tôi đã khai báo việc sử dụng AI.
## 1 - Specification và phạm vi thay đổi
Người dùng gửi ảnh chứng từ, hệ thống nhận job dài và cho theo dõi tiến trình. Nếu response bị mất, gửi lại cùng thao tác phải trả về job cũ, không tạo thêm công việc hoặc kết quả nghiệp vụ. Baseline đã có durable job, worker, retry và UI polling; phần mở rộng trong bài bổ sung Location trong response 202 để client biết URL theo dõi và kiểm chứng các invariant hiện có.
| AC | Acceptance criterion có thể kiểm thử |
|---|---|
| AC1 | POST hợp lệ trả 202, identity đúng, Location trỏ đúng GET job; monitor có state/stage và no-store, không chờ inference. |
| AC2 | Cùng document/key trả cùng job/run reservation và một CREATE_JOB; khác key khi đang active trả 409. Cùng key ở document khác độc lập. |
| AC3 | Retry/recover/cancel và completion lặp hoặc stale không tạo quá một committed run/JOB_COMPLETED cho logical job. |
| AC4 | Anonymous 401; foreign owner 404; thiếu CSRF 403; key sai 400; request bị từ chối không tạo job. |
| AC5 | Harness 200 client đồng thời: đủ 200 outcomes, 0 lỗi, p95 admission ≤ 5,0 giây. Công bố môi trường và giới hạn. |
### Constraints và invariant
- Java là bên ghi business DB; compute chạy ngoài web request/DB transaction. Không thêm queue hoặc model trong Java.
- Giữ body/schema, session/CSRF/ownership; chỉ thêm HTTP header. Không coi reserved result_run_id là kết quả đã tồn tại.
Invariant: cùng (document_id, request_key) chỉ một logical job/CREATE_JOB; duplicate hoặc stale completion không thêm committed run/audit hoàn tất. Đây là kiểm soát side effect, không phải exactly-once computation. Chưa có notification sender nên không nhận đã chứng minh gửi thông báo đúng một lần.
<!-- PAGE -->
## 2 - AI-assisted plan và review bằng source
Em sử dụng Codex để hỗ trợ lập kế hoạch, soạn kiểm thử trước khi sửa code và chạy kiểm chứng. Claude hỗ trợ đối chiếu kế hoạch và phản biện kết quả. Các đề xuất được đánh giá theo source, contract và log thực thi; phụ lục A ghi mục đích sử dụng công cụ, trích đoạn prompt và quyết định sửa hoặc bác bỏ.
### Plan trước implementation
- Bước 1: Chốt baseline/branch riêng; đọc DocumentController, DocumentService, JobService, JobWorker, SecurityConfig và OpenAPI.
- Bước 2: Sinh tests API/DB và mapping trước; chạy baseline, phân biệt lỗi harness, oracle sai và lỗi sản phẩm.
- Bước 3: Thêm ResponseEntity 202 + Location ở createJob; giữ body, Security cache headers và GET; đồng bộ OpenAPI.
- Bước 4: Chạy green, tạo mutant mapping trên nhánh tạm độc lập; lưu assertion fail và xác minh nhánh nộp còn source đúng.
- Bước 5: Đo coverage, thử thứ tự tests, tải 200 client và Chrome/TCP; ghi giới hạn, README và traceability.
### Những điểm của plan AI được sửa hoặc bác bỏ
| Đề xuất ban đầu | Evidence và quyết định |
|---|---|
| Dựng thêm executor/queue mới | JobService và JobWorker đã có claim/lease/fence, scheduler và async executor. Giữ nguyên; tránh hai cơ chế điều phối. |
| Đặt result_run_id = null trước khi hoàn tất | OpenAPI Job yêu cầu string; JobService.create cấp UUID trước compute. Giữ reservation và kiểm persisted ExtractionRun riêng. |
| Thêm explicit CacheControl cho cả POST/GET | SecurityConfig đã trả no-cache, no-store, max-age=0, must-revalidate. Claude chỉ ra override có thể mất header sẵn có; bỏ phần patch dư thừa. |
| Dùng p95 ≤ 5,0 giây làm SLA hoàn tất OCR | Worker/model/hardware không được đo trong harness. Chốt admission API; không suy ra inference hoặc PostgreSQL production SLA. |
### Patch và assumptions
Plan ban đầu dự kiến đổi createJob và GET monitor trong DocumentController.java, cập nhật openapi.json, thêm Vt030AsyncContractTest, Vt030MappingTest và Vt030LoadTest. Sau review bỏ GET/CacheControl và không thêm queue. Production thực tế chỉ đổi DocumentController.java và openapi.json. Phần bổ sung gồm ba lớp kiểm thử trên, hai script mutation/browser và tài liệu riêng. Không đổi JobService, schema body, migrations hoặc UI. Location là URL tương đối; đọc monitor vẫn cần session của owner, không phải bearer capability.
Retry một thao tác cần giữ nguyên key. api.js hiện sinh key mới mỗi lần gọi createJob; kết quả kiểm phía server và replay qua browser chưa chứng minh được UI tự retry với cùng key khi response bị mất.
<!-- PAGE -->
## 3 - Risk strategy, partitions và test cases (1/2)
Unit kiểm mapping giữa ba ID khác nhau. Integration/API kiểm Security, controller, JPA/Flyway và H2; service tests kiểm claim/fence/transaction. E2E dùng Chrome/TCP; tải API được đo riêng.
Các lớp tương đương được chọn theo quyết định xử lý của hệ thống. Mỗi nhóm dưới đây có đại diện cho các kết quả khác nhau; độ dài key 1, 100 và 101 bổ sung kiểm tra biên.
| Nhóm đầu vào | Lớp tương đương | TC đại diện |
|---|---|---|
| Khóa yêu cầu | Hợp lệ; vắng; sai ký tự; quá dài | TC01, TC19; TC14; TC05; TC20 |
| Phạm vi retry | Cùng document/key; khác key khi active; khác document | TC03; TC04; TC09 |
| Quyền truy cập | Chủ sở hữu; người dùng khác; chưa xác thực | TC01; TC08; TC07 |
| Trạng thái job | Active; retrying; succeeded; failed; cancelled | TC04; TC11; TC10; TC15; TC12 |
| Claim | Token cũ; lease hết hạn | TC11; TC13 |
| Quota | Tạo mới khi hết quota; replay key cũ | TC21 |

| ID | AC/risk; level | Precondition/input | Expected result | Pri. |
|---|---|---|---|---|
| TC01 | AC1/identity; API | Owner+CSRF, ảnh synthetic, key mới | 202; đúng doc/job, Location đúng; QUEUED; 0 run | P1 |
| TC02 | AC1/stale view; API | Poll job đã nhận | no-store, đúng document/state; không lease token | P1 |
| TC03 | AC2/lost response; API/DB | Gửi lại cùng doc/key | Cùng job/run reservation; 1 Job/CREATE_JOB | P1 |
| TC04 | AC2/duplicate; API/DB | Active job, key khác | 409; không insert thêm | P1 |
| TC05 | AC4/invalid key; API/DB | Key có space/slash | 400; 0 Job | P1 |
| TC06 | AC4/CSRF; API/DB | Có session, thiếu CSRF | 403; 0 Job | P1 |
| TC07 | AC4/privacy; API | Anonymous đọc monitor | 401; không lộ progress | P1 |
| TC08 | AC4/ownership; API/DB | Foreign owner đọc/tạo job | 404; số job không đổi | P1 |
| TC09 | AC2/key scope; service/DB | Cùng key, hai documents receipt/invoice | Hai job độc lập, mỗi doc 1 Job | P1 |
Mẫu synthetic receipt-demo.png/invoice-demo.png có sẵn; mỗi API case có user/document riêng. Unit dùng ba UUID cố định khác nhau; TC09 chỉ kiểm phạm vi key giữa hai loại tài liệu.
<!-- PAGE -->
## 3 - Risk strategy và test cases (2/2)
| ID | AC/risk; level | Precondition/input | Expected result | Pri. |
|---|---|---|---|---|
| TC10 | AC3/duplicate completion; service/API/DB | Complete hai lần, replay sau success | Lần hai false; 1 run/JOB_COMPLETED; không thêm audit | P1 |
| TC11 | AC3/transient; service/API | Retryable failure, claim mới, old complete | RETRYING; old fence reject; new complete một lần | P1 |
| TC12 | AC3/cancel race; service/API | Cancel RUNNING, late complete | CANCELLED; 0 committed run | P1 |
| TC13 | AC3/lease; service/DB | Lease=Instant.EPOCH; recover/claim lại | Old token reject, new complete; 1 run | P1 |
| TC14 | AC2/no key; API/DB | Submit không key hai lần khi active | 202 rồi 409; 1 Job | P2 |
| TC15 | AC3/terminal; service/API | Permanent fail; replay original key | Cùng FAILED job, 0 run | P1 |
| TC16 | AC1/mapping; unit | 6 states, IDs job/doc/run khác nhau | document_id luôn là owning document | P1 |
| TC17 | AC5/fan-out; load API | 200 users/docs, barrier 200 | 200 responses/Jobs/CREATE_JOB, p95 ≤ 5,0 giây | P1 |
| TC18 | AC2/retry storm; load API | 200 client cùng owner/doc/key | Cùng ID; 1 Job/CREATE_JOB; 0 lỗi | P1 |
| TC19 | AC2/valid length; API | Key dài 1 và 100 | Cả hai accepted trên doc riêng | P2 |
| TC20 | AC4/overlong; API | Key dài 101 | 400; 0 Job | P2 |
| TC21 | AC2/quota; API | Owner có 5 active; tạo thứ 6/replay cũ | New 429; không insert; replay cũ 202 | P1 |
| E2E01 | AC1/UX; Chrome/TCP | Login/upload receipt; worker tắt | 202/Location; UI QUEUED và poll đúng | P1 |
| E2E02 | AC2/replay; browser API | Giữ session/key submit đầu | Same job, document detail cùng ID | P1 |
| E2E03 | AC3/status; Chrome/TCP | Cancel QUEUED qua session+CSRF | CANCELLED; progress active biến mất | P2 |
TC05–08/20 là negative tests; TC11/13/15 là failure paths. 21 case IDs tạo 27 JUnit invocations do TC16 có 6 states và TC19 có 2 độ dài; 3 browser checks được báo riêng, không cộng lặp những lần chạy lại.
Không cần retrain, payment, thêm notification provider hoặc lặp mọi UI case ở unit trong phạm vi bài này. PostgreSQL locking, native OCR/model và crash thật vẫn cần integration về sau; H2 và cập nhật timestamp không thay thế các phép kiểm đó.
<!-- PAGE -->
## 4 - Test-first: fail → patch → pass
Baseline 729be6f đã có async worker và progress UI. Phần mới cần chứng minh là response có monitor URL đúng và không làm hỏng retry/ownership. Test-first commit 2d34f4c10cc4b8a692982be93ac0b4d6c6643d28 chưa chứa production patch.
| Lượt | Kết quả thực tế; phân loại |
|---|---|
| red (sandbox) | MSYS không khởi động; không tính là behavioral red. |
| red-native | 15 API/service tests (chưa chạy 6 unit), 2 failures: thiếu Location thật; cache header assertion quá chặt là lỗi test. |
| red-reviewed | Sửa cache oracle thành chứa directive no-store: 21 tests, 1 failure, 0 errors/skips. Chỉ TC01 fail vì Location null. |
| green | Sau patch và bổ sung key/quota cases: 25 tests, 0 failures/errors/skips. |
| full-coverage / final-full-coverage | Mỗi lượt 50 Java tests, 0 failures/errors/skips; JAR/JaCoCo đạt. 27 invocations mới VT-030; 23 baseline. Lượt cuối sau khi siết quota replay. |
Patch commit e3b3850000fa0a8f8f499bbc7ae7a88f06fdbc3d chỉ thêm monitor header trong flow hiện có:
```java
DocumentService.JobView job = jobs.create(id, user.id(), key);
return ResponseEntity.accepted()
    .location(URI.create("/api/v1/jobs/" + job.id()))
    .body(job);
```
### Mutation bắt buộc: đổi response-field mapping
Nhánh tạm experiment/vt030-response-mapping, commit 09cd8a2169eade641bca2a4a426411736d37c029, đổi đúng một argument trong DocumentService.jobView: document_id lấy j.id thay vì j.documentId. Nhánh này chỉ local, không đưa vào nhánh nộp hoặc merge.
Chạy TC01 và 6 representatives TC16: JUnit XML ghi 7 tests, 7 failures do sai identity; không phải compile/setup error. TC01 dùng document ID được upload, TC16 dùng UUID cố định riêng; oracle không gọi lại chính mapper. Bug bị phát hiện ở unit và API boundary.
Experiment trước đó trên working copy cũng killed mutant và restore đúng SHA-256. Sau restore, full suite đạt. Experiment nhánh tạm độc lập không sửa nhánh nộp; hash mapper vẫn d99f5201…6f60f. Log/patch/commit và kiểm source unchanged có trong evidence/mutation-branch.*; đây là một mutant có chủ đích, không phải mutation score tổng quát. Tool sau review đọc fresh JUnit XML thay tìm chuỗi log; Windows mutation chạy lại 7 failures/0 errors và restore đúng hash (windows-mutation.*).
<!-- PAGE -->
## 5 - Coverage và thử tải 200 client
JaCoCo 0.8.14 đo trong lượt final-full-coverage gồm 50 tests trên source đúng; counters trùng lượt full-coverage ban đầu. Không gộp coverage từ mutant hoặc từ nhiều run không kiểm soát.
| Phạm vi | Line covered/total | Branch covered/total |
|---|---|---|
| Backend toàn bộ | 1.162/1.441 = 80,64% | 450/710 = 63,38% |
| JobService | 143/162 = 88,27% | 40/62 = 64,52% |
| DocumentController.<br/>createJob | 4/4 = 100% | N/A: không có branch counter |
| DocumentService.<br/>jobView | 1/1 = 100% | N/A: không có branch counter |
100% line ở mapper không đảm bảo mapping đúng: mutant vẫn đi qua dòng đó nhưng sai ý nghĩa. Semantic assertions bắt bug; risk coverage AC1–AC5 nằm ở trang 7. Phần branch chưa cover của JobService và controller/service khác vẫn là hạn chế của suite.
### Thiết kế harness và số đo
Môi trường: Windows 11, Ryzen 7 8840HS, 8 cores/16 logical processors, RAM 15,21 GiB; Java 17.0.20.1+1, Spring Boot 3.5.16, H2 in-memory, Hikari pool 10. User, session và document synthetic được tạo trước phép đo; worker được tắt trong thử tải.
Cách đo: 200 threads cùng chờ ready latch rồi được release; nanoTime đo từng request qua MockMvc, Spring Security và JPA. Deadline là 60 giây; mọi outcome, kể cả lỗi hoặc timeout, đều được giữ. p95 là mẫu thứ ceil(0,95 × 200) = 190 sau sắp tăng. Readiness/count được assertions kiểm; peak inflight là số đo. Timer mỗi request bắt đầu khi thread xử lý sau release, còn timeout tính từ release; các run được so sánh đều có 0 lỗi.
| Run/JVM mới | 200 users/docs độc lập | 200 retry cùng key | Lỗi / peak inflight |
|---|---|---|---|
| load-repeat1 | p95 2.252,13 ms; 200 Jobs | p95 205,40 ms; 1 Job | 0 ở mỗi kịch bản; 200/200 |
| load-repeat2 | p95 2.244,73 ms; 200 Jobs | p95 222,96 ms; 1 Job | 0 ở mỗi kịch bản; 200/200 |
Cả hai kịch bản đạt p95 ≤ 5,0 giây trong hai run chính; CREATE_JOB counts tương ứng 200 và 1. Raw JSON giữ đủ 200 outcomes/run/scenario. Lượt full-coverage ban đầu có instrumentation/warm-up khác cho 178,56/180,51 ms, retry peak 195; chỉ dùng như phép kiểm bổ sung, không chọn số nhanh nhất để báo SLA. Warm-up/thứ tự có thể ảnh hưởng chênh lệch, nhưng chưa tách thành thí nghiệm nhân quả; không kết luận chi phí riêng của mỗi scenario từ các số này.
Giới hạn: số đo áp dụng cho bước nhận job trong MockMvc/H2. Thời gian login, upload và chuẩn bị fixture nằm ngoài timer; chưa đo PostgreSQL production, OCR/model, GPU hoặc gửi thông báo. Chrome/TCP được kiểm chức năng riêng với một session; chưa có TCP load test 200 người dùng.
<!-- PAGE -->
## 6 - Traceability, flaky review và residual risk
Các lớp test nằm trong backend/src/test/java/vn/vietdoc/: API/service dùng Vt030AsyncContractTest.java; unit dùng Vt030MappingTest.java; tải dùng Vt030LoadTest.java. E2E dùng scripts/vt030_browser.cjs.
Commit rút gọn dùng thống nhất: 2d34f4c (test-first), e3b3850 (patch và boundary tests), a1055c3 (siết assertions và mutation tool). Full hash ở trang đầu và phụ lục B. TC01–18 có từ test-first; TC19–21 và browser checks được bổ sung sau patch.
| AC/risk | Test, lớp/file và commit | Evidence và giới hạn |
|---|---|---|
| AC1/monitor, mapping | TC01–02: API; TC16: unit — 2d34f4c. E2E01: browser — e3b3850. | Red đúng Location; green API/unit; Chrome poll; mapping mutant bị bắt. |
| AC2/retry duplicate | TC03–04, TC09, TC14: API; TC18: tải — 2d34f4c. TC19, E2E02 — e3b3850. TC21 — e3b3850, a1055c3. | API/DB audit invariants và 200 same-key đạt; UI auto-retry chưa kiểm chứng. |
| AC3/recovery, late effects | TC10–13, TC15: API/service — 2d34f4c. E2E03: browser — e3b3850. | Một committed run/audit; stale/cancel reject. Service simulation, chưa kill process thật. |
| AC4/access/input | TC05–08: API — 2d34f4c. TC20: API — e3b3850. | 400/401/403/404 đúng, không insert; phạm vi kiểm tra là các endpoint trong bài. |
| AC5/200 client; p95 ≤ 5,0 giây | TC17–18: tải — 2d34f4c, e3b3850. | Hai fresh-JVM runs đạt; raw outcomes và count DB; scope MockMvc/H2 admission. |
### Kiểm tra flaky tests
- Time: TC13 đặt lease quá hạn bằng Instant.EPOCH thay sleep; latency dùng monotonic nanoTime. Chưa kiểm clock skew giữa nhiều host.
- Order/shared state: mỗi API case có owner/doc riêng; hai JVM chạy JUnit method seeds 17 và 83 đều 25/25 pass. order-comparison.json xác nhận thứ tự case ghi trong XML của hai seed khác nhau và khác green; final-order-seed17 và final-order-seed83 kiểm lại sau commit a1055c3. Class-order seed ở log; hai lần chưa đủ kết luận hết flaky.
- Concurrency: barrier đủ 200 trước release; future deadline, giữ lỗi và shutdown/await pool. Ở hai run chính peak inflight thực tế là 200; DB/audit counts kiểm side effects, không chỉ HTTP status.
- Network/random: browser chờ response/selector có điều kiện và readiness, không sleep cố định để đoán UI đã xong. UUID chỉ để isolation, không làm expected identity. Browser một lượt đạt, chưa đủ đánh giá tỷ lệ flaky dài hạn.
### Test tiếp theo có giá trị cao
P1: PostgreSQL thật, hai runner tranh claim, kill sau effect trước ACK rồi replay cùng key; kiểm một committed run/audit. P1: UI mất response và tự retry giữ nguyên key. P2: actual-provider E2E/capacity trên cấu hình model được chốt; integration notification chỉ khi có module đó. Các mục này chưa được nhận là đã hoàn thành.
<!-- PAGE -->
## 7 - Reflection
Qua bài này, confidence của em tăng khi cùng một contract được kiểm ở nhiều ranh giới. Test đầu tiên xác nhận đúng document ID và URL monitor, thay vì chỉ nhìn HTTP 202. Lần red đã được kiểm lại: một failure là thiếu Location thật, còn failure cache header đến từ oracle quá chặt. Nếu giữ nguyên assertion đó, em sẽ sửa production code để chiều một test sai.
Mutation giúp đánh giá giá trị của assertion rõ hơn coverage. Khi document_id bị lấy từ job.id, cả API case và sáu state representatives đều thất bại vì identity sai. Hai loại test dùng expected ID độc lập với mapper. Vì vậy, việc mutant bị bắt có ý nghĩa hơn một dòng mapper được đánh dấu đã chạy. Tuy nhiên, một mutant không chứng minh suite bắt được mọi lỗi mapping hoặc race condition.
Điểm chưa được chứng minh là hành vi trên PostgreSQL thật và khi process chết giữa side effect với acknowledgement. H2 vẫn hữu ích để chạy nhanh transaction và ownership cases, nhưng không đủ thay kết quả của database triển khai. Tương tự, p95 dưới năm giây chỉ thuộc bước nhận job trong harness. Nó không nói rằng hai trăm hóa đơn sẽ được OCR xong trong năm giây.
Bước kiểm tiếp theo đáng làm nhất là chạy hai runner trên PostgreSQL, cố ý kill một runner sau completion rồi phát lại cùng request key. Oracle cần kiểm số committed run và audit, không chỉ trạng thái cuối. Em cũng cần kiểm UI tự retry khi response bị mất, vì helper hiện sinh key mới mỗi lần gọi. AI hỗ trợ tạo giả thuyết, sinh code và phản biện; các kết luận chỉ được sử dụng khi đối chiếu được với source, assertions, logs và phạm vi kiểm chứng đã công bố.
### Đối chiếu nguồn học và bài trước
Lecture 06: slides 9–10 về Spec/Plan/Verify và mini-spec; 14/18 về checkpoint và kiểm độc lập; 26 về evidence. Lecture 07: slides 13 về equivalence partitioning, 18 về giới hạn coverage, 21 về flaky risks, 23–24 về test quality/mutation. Em áp dụng vào increment cụ thể, không dùng slide thay runtime evidence.
BT2 AD-030 chỉ được dùng để giữ thông tin sinh viên và cách trình bày. Bài này dùng đúng VT-030, 200 client và p95 5,0 giây; không mang số đo 379 client hoặc 3,5 giây của BT2 sang. Test code, fixtures và mutation trong bài là increment riêng trên baseline được chỉ rõ.
<!-- PAGE -->
## Phụ lục A - Sử dụng AI và quyết định kiểm chứng
Em sử dụng Codex và Claude để hỗ trợ các bước lập kế hoạch, soạn kiểm thử, đề xuất patch và phản biện. Bảng dưới đây tóm tắt mục đích yêu cầu và quyết định sử dụng kết quả.
| Giai đoạn và công cụ | Mục đích yêu cầu (tóm tắt) | Output và quyết định |
|---|---|---|
| Lập kế hoạch — Codex, Claude | Đối chiếu VT-030 với source; chọn phần thay đổi nhỏ; nêu assumptions, file dự kiến và tests trước implementation. | Chọn bổ sung Location; giữ JobService, worker và body contract. Bác bỏ queue mới, nullable result_run_id và CacheControl dư thừa. |
| Soạn và kiểm tra tests — Codex | Kiểm monitor URL, identity, retry, ownership và failure paths; xác nhận test fail đúng nguyên nhân trước patch. | red-native có một oracle cache quá chặt. Sửa assertion theo directive no-store; red-reviewed còn đúng một lỗi Location. |
| Patch và mutation — Codex | Thêm header theo contract; đổi mapping document_id trên nhánh thử nghiệm để đánh giá assertions. | Patch giới hạn ở controller và OpenAPI; mutation bị 7 tests phát hiện. Source đúng được khôi phục trước chạy lại suite. |
| Phản biện kết quả — Claude; chỉnh sửa — Codex | Rà yêu cầu, traceability, phép đo tải, chất lượng assertions và giới hạn kết luận. | Siết TC21, chuyển kiểm mutation sang fresh JUnit XML, đối chiếu thứ tự tests và chạy lại. Full suite cuối đạt 50 tests; chi tiết ở peer-review.md. |
### Trích đoạn prompt đã sử dụng
“Please return a concrete implementation plan BEFORE code,<br/>then WRITE TEST CODE AS TEXT ONLY”
Trích đoạn trên nằm trong evidence/ai-plan-prompt.md. Yêu cầu đầy đủ kèm source đã chọn; phản hồi được lưu ở evidence/ai-plan-response.md. Prompt và phản hồi của lượt rà kết quả nằm trong ai-final-prompt.md và ai-final-review.md cùng thư mục.
### Hai đề xuất AI cần kiểm tra lại
- Assertion Cache-Control bằng đúng no-store có vẻ hợp lý nhưng loại một response hợp lệ của Spring Security. Đối chiếu SecurityConfig cho thấy cần kiểm sự hiện diện của directive, không ép toàn bộ chuỗi header.
- Đặt result_run_id thành null trước completion có vẻ phản ánh trạng thái tốt hơn, nhưng trái OpenAPI và cơ chế reserve UUID. Việc kết quả đã tồn tại phải kiểm bằng ExtractionRun, không suy từ ID được trả về.
Các quyết định sửa/bác bỏ được đối chiếu với source và evidence tại red-native, red-reviewed, windows-mutation, final-full-coverage và order-comparison.json. Nhánh bài tập chưa được nhóm review hoặc merge.
<!-- PAGE -->
## Phụ lục B - Evidence có thể chạy lại
Thư mục docs/assignments/vt030/evidence chứa raw logs, command metadata, JUnit XML, coverage XML, hardware, browser kết quả/ảnh và load outcomes. Logs công khai được redacted synthetic session tokens; metadata redaction ghi hashes trước/sau. Không sửa assertion, counts hoặc kết quả để làm đẹp evidence.
### Trích kết quả, phân biệt đúng nguyên nhân
```text
red-reviewed: Tests run: 21, Failures: 1, Errors: 0
TC01: expected Location /api/v1/jobs/{job_id}, actual null
mutation branch: Tests run: 7, Failures: 7, Errors: 0
Assertion: response field must map to owning document
green: Tests run: 25, Failures: 0, Errors: 0
full-coverage: Tests run: 50, Failures: 0, Errors: 0
order-seed17 / order-seed83: each 25 tests, 0 failures
browser: E2E01, E2E02, E2E03 PASS; owned JVM stopped
```
### Commit đối chiếu
- Test-first: 2d34f4c10cc4b8a692982be93ac0b4d6c6643d28.
- Patch: e3b3850000fa0a8f8f499bbc7ae7a88f06fdbc3d.
- Bổ sung assertions/tool: a1055c300f2321ba64f0f46582348f63b258a542.
### Lệnh ngắn (working directory backend)
```text
./mvnw -Dtest=Vt030AsyncContractTest,Vt030MappingTest test
./mvnw -Dtest=Vt030LoadTest test
./mvnw -Dtest='*Test' package
```
Windows dùng .\mvnw.cmd thay ./mvnw. Coverage dùng JaCoCo prepare-agent trước test và report sau test, version 0.8.14. README trong nhánh chứa câu lệnh đầy đủ, JVM flags, browser prerequisites và cách đọc JSON; command metadata giữ cả Maven settings/cache của máy chạy, không buộc máy khác có cùng ổ D:.
Test-first commit 2d34f4c có thể checkout riêng để tái hiện red-reviewed (21 tests, 1 fail Location). Patch e3b3850 chứa source và cases bổ sung. Không chạy mutant trực tiếp trên working tree đang có thay đổi; tạo checkout tạm rồi chạy scripts/vt030_mutation.py; script restore bytes trong finally. Commit mutant 09cd8a2 chỉ local, patch của nó kèm trong evidence để đối chiếu.
Lệnh PowerShell focused trong README đã chạy 25/25 pass (windows-wrapper.*); tool mutation dùng cmd/mvnw.cmd cũng đã chạy và restore. Các command còn lại là hướng dẫn tương đương; exact argv/env từng run ở JSON. history.txt và source-baseline-proof.json đối chiếu commit, thời gian và blob: commit 2d34f4c chưa đổi production. Metadata red lịch sử không lưu git SHA trực tiếp, không dựng lại bằng chứng đó.
Raw load-baseline log là thăm dò trước patch, không dùng làm kết quả cuối. Hai XML cũ bị runner copy theo timestamp thư mục được loại khỏi tập reports hợp lệ; audit curation ghi rõ, không tính lại vào coverage hoặc tổng test. Benchmark chính là load-repeat1/2; không cộng các run lặp thành số test cases mới.
<!-- PAGE -->
## Phụ lục C - Kiểm UI trên trình duyệt thật
Worker được tắt có chủ đích để QUEUED đủ lâu cho UI polling kiểm ổn định; test không giả lập tiến trình OCR. JAR demo chạy loopback 127.0.0.1:18830 với H2 riêng, ảnh receipt-demo.png synthetic; Chrome đi qua login, upload và API thật. Replay giữ cookie/key nhưng là thao tác automation, chưa phải tính năng automatic retry của UI.
![Hình C1 - UI hiển thị trạng thái chờ của job đã được API nhận; ảnh từ browser check E2E01.](evidence/browser-queued.png)
Sau đó E2E02 gửi lại đúng key và xác nhận job ID không đổi; E2E03 hủy job, UI ngừng hiện progress active sau polling. browser.json lưu ba PASS; browser-runtime.json xác nhận JVM thuộc phép thử đã dừng. Đây là một E2E session chức năng, không phải chứng minh độ bền dài hạn hay tải TCP 200 người.
### Tài liệu đối chiếu
- Đề cá nhân VT-030 do giảng viên cung cấp; baseline/source và test files ở nhánh nộp.
- Lecture_06_AI_Assisted_Software_Development_and_Vibe_Coding_v3.pptx, 27 slides; Lecture_07_Software_Testing_and_Quality_Engineering.pptx, 28 slides.
- [JaCoCo Maven plugin – tài liệu chính thức](https://www.jacoco.org/jacoco/trunk/doc/maven.html). Tool chạy được pin 0.8.14, không lấy version snapshot trong trang hướng dẫn làm kết quả đo.
- Bài BT2_23001870_AD-030.pdf: tham khảo bố cục và định danh; không dùng làm bằng chứng runtime cho VT-030.
