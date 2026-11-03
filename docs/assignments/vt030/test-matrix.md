# Risk strategy và equivalence partitioning VT-030

Mọi case dưới đây là test cá nhân mới, không dùng số pass của review nhóm để nhận credit. ID mapping tương ứng method `tcXX...`; unit TC16 có6 state representatives; TC19 có2 length representatives. Test level đã thực thi sẽ theo evidence, không suy từ tên class.

| ID | AC / risk | Level | Partition, precondition/input | Expected oracle | Priority |
|---|---|---|---|---|---|
| TC01 | AC1/identity, discovery | API/DB | Owner+CSRF, document mới, valid key | 202, Location dùng job.id khác document_id; QUEUED/WAITING;0 persisted run | P1 |
| TC02 | AC1/stale UI | API/DB | Poll existing QUEUED job | no-store directive, correct document/state; không lease token | P1 |
| TC03 | AC2/response loss | API/DB | Replay cùng doc/key | Same job/reserved run;1Job+1CREATE_JOB audit | P1 |
| TC04 | AC2/duplicate active | API/DB | Active job, key khác |409 ACTIVE_JOB_EXISTS; không insert | P1 |
| TC05 | AC4/key injection | API/DB negative | Key chứa space/slash |400 INVALID_IDEMPOTENCY_KEY;0Job | P1 |
| TC06 | AC4/CSRF | API/DB negative | Authenticated nhưng thiếu CSRF |403;0Job | P1 |
| TC07 | AC4/privacy | API negative | Anonymous polling private ID |401; không lộ progress | P1 |
| TC08 | AC4/ownership | API/DB negative | Foreign owner read/enqueue ID đã có |404; job count giữ1 | P1 |
| TC09 | AC2/key scope | Service/DB | Same key, hai documents khác type | Hai job IDs khác, mỗi doc1Job | P1 |
| TC10 | AC2/AC3/duplicate effect | Service+API/DB | Complete cùng claim2lần, retry same key sau success | Lần2false;1run, audit count không tăng | P1 |
| TC11 | AC3/transient failure | Service+API/DB failure path |503-like retryable failure, new claim, late old completion | RETRYING; old fence reject; new complete once | P1 |
| TC12 | AC3/cancel race | Service+API/DB | Cancel RUNNING rồi late complete | CANCELLED;0run | P1 |
| TC13 | AC3/recovery/time | Service/DB | leaseUntil=Instant.EPOCH, không sleep | Recover RETRYING, new token; old reject;1run | P1 |
| TC14 | AC2/no key | API/DB | Absent key rồi submit lần2 khi active | First202, second409;1Job | P2 |
| TC15 | AC3/terminal replay | Service+API/DB | Permanent failure, replay original key | Same FAILED job;0run; không tự tạo job mới | P1 |
| TC16 | AC1/mapping mutation | Unit |6 job states, fixed distinct job/document/run IDs | documentId luôn owning document, không map từ job.id | P1 |
| TC17 | AC5/fan-out | Concurrent API harness |200 independent users/docs, seeded synthetic sessions, barrier200 |200 outcomes202,200Jobs/audits; p95<=5000ms | P1 |
| TC18 | AC2/AC5/retry storm | Concurrent API harness |200 same-key clients, one owner/doc |200 responses same ID;1Job/CREATE_JOB; errors0 | P1 |
| TC19 | AC2/valid-key class | API/DB | Key lengths1 và100, valid ASCII | Accepted;1Job per isolated doc | P2 |
| TC20 | AC4/invalid-length class | API/DB negative | Key length101 |400 và0Job | P2 |
| TC21 | AC2/resource admission | API/DB | Owner có5active jobs, submit thứ6; replay key cũ | New429 không insert; replay cũ vẫn202 | P1 |
| E2E01 | AC1/progress UX | Browser/TCP | Login/upload synthetic receipt, worker disabled |202+Location, UI QUEUED, actual poll correct | P1 |
| E2E02 | AC2/response replay | Browser session/API | Reuse key/cookie từ submit qua browser | Same job ID persisted in document detail | P1 |
| E2E03 | AC3/status termination | Browser/TCP | Cancel queued job bằng CSRF session thật | CANCELLED và active progress biến mất sau polling | P2 |

## Vì sao là equivalence partitioning

Chia theo quyết định của hệ thống, không chỉ chọn số tùy ý: valid/absent/malformed/overlong keys; same/different key và same/different document; owner/foreign/anonymous; active/retrying/succeeded/failed/cancelled; current/stale/expired claim; quota below/at/exceeded. Mỗi partition có expected behavior khác nhau nên cần representative riêng. Length1/100/101 bổ sung boundary kiểm class, không thay equivalence classes bằng chỉ boundary testing. Receipt/invoice ở TC09 kiểm key scoping, không là bằng chứng extraction quality.

## Chọn layer và phần không cần ở increment này

Unit TC16 bảo vệ semantic mapping; API tests dùng MockMvc đi qua Spring Security/controller/JPA/Flyway với H2 thật (không mock JobService). Service cases kiểm transaction/fence/run invariants. Browser/TCP kiểm người dùng nhìn thấy progress và same-session replay. Load dùng barrier200, Hikari10 và all-outcome percentile; prep/seed tách khỏi timed admission.

Không cần retrain/model accuracy, general-document extraction, payment integration, thêm notification provider, queue mới hoặc lặp tất cả browser cases ở mọi unit. Không cần H2 chứng minh PostgreSQL lock semantics: PG distributed/race/kill recovery là residual test ưu tiên, không giả đã chạy. Không đo200fullOCR nếu không có model/hardware. Không tuyên bố thiếu notification bị kiểm exactly-once; hiện chỉ có DB audit side effects.

## Flaky review

Time: TC13 đặt timestamp quá hạn cố định, không đợi sleep; claim deadlines đủ margin; API latency đo monotonic nanoTime. Order/state: mỗi test user/document UUID mới, không dựa order hoặc count global DB; thử method order seeds khác trên JVM/DB mới. Concurrency: ready latch200 trước release, timeout có fail, shutdown/awaitTermination; errors không drop khỏi denominator. Network: unit/API không external calls, browser local loopback/condition waits thay sleep; readiness timeout không ghi app bug nếu JVM chưa chạy. UUID randomness dùng để isolation, không là oracle giá trị đúng.
