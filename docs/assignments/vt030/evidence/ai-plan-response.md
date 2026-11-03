I couldn't write the plan file because this session has no Write or ExitPlanMode tool, and the brief forbids writing anyway. The full plan is below. **Source identity:** context_id `64e373ab…f3dd877`, base `729be6fe`, and the injected file hashes as given.

**Drift notice:** three untracked files appeared in the worktree while I was reviewing: `Vt030AsyncContractTest.java`, `Vt030MappingTest.java` and `Vt030LoadTest.java`. They're not in the frozen snapshot and I didn't review them. Production `DocumentController` still matches baseline (it still has `@ResponseStatus(ACCEPTED)` and no `location(`).

## 1. Corrections to the proposed slice

1. **The no-store header can't be the red reason. Baseline already sends it.** `SecurityConfig.java:36-55` never customises `headers()`. So Spring Security's default `HeaderWriterFilter` (Boot 3.5.16, Security 6.5) adds `Cache-Control: no-cache, no-store, max-age=0, must-revalidate`, plus `Pragma` and `Expires`, to both job endpoints at the MockMvc security-filtered boundary.
   - A `contains("no-store")` check passes on baseline. That includes your draft's `Vt030AsyncContractTest.java:95,103`.
   - Adding an explicit `CacheControl.noStore()` would change the header to exactly `no-store`. Spring Security's `CacheControlHeadersWriter` then skips, so `Pragma` and `Expires` disappear from these two endpoints.
   - **Recommendation:** don't add explicit no-store. Keep the no-store test as a retained check that passes before and after. To prove this, print the actual baseline headers in the red run.
2. **The `Location` header is the only real behaviour change**, so it's the only valid red driver.
3. **The shipped UI doesn't use server-side idempotency.** `api.js:67` creates a fresh `crypto.randomUUID()` key on every `createJob` call. If a UI request is retried after a lost response, it gets 409 while the first job is still active, or creates a new job and run once it has finished. The server tests prove server behaviour only; the client fix belongs to the Web owner.
4. **A completion p95 is impossible by design.** This is from reading the config, not a measurement:
   - The worker claims at most about 1 job per second: `@Scheduled(fixedDelay=1000)` at `JobWorker.java:28`, a single executor at `:20`, and a `busy` flag.
   - So 200 jobs take at least ~200 s, which is more than `job-deadline-seconds: 180` (`application.yml:51`). The tail jobs would end as `DEADLINE_EXCEEDED`.
   - This supports your rejection (c): the p95 claim must cover admission and polling only.

## 2. Implementation plan (in order)

0. **Tests first.** Add `JobAdmissionHttpContractTest` (code below) and run it on baseline. Expected: only T1 fails, with `expected: </api/v1/jobs/<uuid>> but was: <null>`. T2–T4 pass. If T2–T4 fail on baseline, stop and triage before patching. Keep the surefire txt/xml output and the printed baseline headers as evidence.
1. **Production patch: `DocumentController.createJob` only.**
   - Return `ResponseEntity<DocumentService.JobView>`: `var job = jobs.create(id, user.id(), key); return ResponseEntity.accepted().location(URI.create("/api/v1/jobs/" + job.id())).body(job);`
   - Remove `@ResponseStatus` from that method and add `import java.net.URI;`.
   - Don't touch `JobService`, `DocumentService`, `JobWorker`, the GET endpoint or the body shape.
2. **`openapi.json`:** add `headers.Location` (string, relative, owner session still required) to the 202 response of `POST /documents/{id}/jobs`. This is an additive change.
   - I didn't read `BusinessContractTest`, `DemoConfigurationTest` or `specs/`. Rerun the first two and check `specs/` for stale text.
3. **Green run:** rerun the new class, then the full backend suite, and record the counts.
4. **Mutation run:**
   - Byte-copy `DocumentService.java` to `tmp/bt3-vt030/mutation/`.
   - Apply mutant M1: in `jobView`, change the second constructor argument from `j.documentId` to `j.id`.
   - Run the new class, then `WorkflowIntegrationTest` separately. Prediction to verify: M1 survives the existing suite and is killed by T2 and T3.
   - Restore by copy, then check the sha256 equals `d99f5201…` and `git diff --exit-code` on the file exits 0. Rerun green.
   - Optional extra mutants: M2 (`id` ← `j.resultRunId`, killed by T1–T4) and M4 (controller `Location` built from `documentId`, killed by T1).
5. **Load harness:** opt-in, after the patch, in 3 separate JVM runs. Report every run.
6. **Diff review:** only `DocumentController.java`, `openapi.json` and the new tests should change.

## 3. Test code (text only, compiles against baseline APIs)

```java
package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.*;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.common.Json;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.integration.AiClient;
import vn.vietdoc.job.JobService;
import vn.vietdoc.persistence.Store;

/** Oracles = path/upload ids + raw SQL rows; never DocumentService.jobView/jobs.get output. */
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:vt030contract;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
    "vietdoc.worker-enabled=false", "vietdoc.mode=demo",
    "vietdoc.pipeline-manifest=fictional-fixtures.v1", "vietdoc.storage=./target/test-storage"})
@AutoConfigureMockMvc
class JobAdmissionHttpContractTest {
  @Autowired MockMvc mvc;
  @Autowired AuthService auth;
  @Autowired DocumentService documents;
  @Autowired JobService jobs;
  @Autowired AiClient ai;
  @Autowired Json json;
  @Autowired JdbcTemplate jdbc;

  record Client(AuthService.Identity user, MockHttpSession session) {}

  /** Real session token read by the real SecurityConfig filter; avoids the 15/min HTTP login limiter. */
  Client client() {
    String name = "vt030-" + Store.id();
    auth.seed(name, "integration-password");
    Map<String, Object> login = auth.login(name, "integration-password");
    MockHttpSession session = new MockHttpSession();
    session.setAttribute("vietdoc-token", login.get("access_token"));
    return new Client((AuthService.Identity) login.get("user"), session);
  }

  String upload(Client c) throws Exception {
    var file = new MockMultipartFile("file", "receipt-demo.png", "image/png",
        Files.readAllBytes(Path.of("../samples/receipt-demo.png")));
    return documents.upload(c.user().id(), file, "receipt", Store.id()).id();
  }

  MvcResult create(Client c, String documentId, String key) throws Exception {
    MockHttpServletRequestBuilder r =
        post("/api/v1/documents/{id}/jobs", documentId).session(c.session()).with(csrf());
    if (key != null) r.header("Idempotency-Key", key);
    return mvc.perform(r).andReturn();
  }

  JsonNode body(MvcResult r) throws Exception {
    return json.read(r.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }
  int count(String sql, Object... args) { return jdbc.queryForObject(sql, Integer.class, args); }
  int audits(String doc, String action) {
    return count("select count(*) from audit_events where document_id = ? and action = ?", doc, action);
  }
  String onlyJobId(String doc) {   // throws if not exactly one row
    return jdbc.queryForObject("select id from jobs where document_id = ?", String.class, doc);
  }
  static void assertStatus(int expected, MvcResult r) throws Exception {
    assertEquals(expected, r.getResponse().getStatus(), r.getResponse().getContentAsString());
  }
  void assertError(MvcResult r, int status, String code) throws Exception {
    assertStatus(status, r);
    if (code != null) assertEquals(code, body(r).path("error").path("code").asText());
  }
  static void assertNoStore(MvcResult r) {
    String cc = r.getResponse().getHeader("Cache-Control");
    assertNotNull(cc, "Cache-Control missing");
    assertTrue(Arrays.stream(cc.split(",")).map(String::trim).anyMatch("no-store"::equalsIgnoreCase), cc);
  }

  /** T1 – RED on baseline: Location is null. Only intended red test. */
  @Test
  void acceptedJobAndKeyedReplayExposeTheSameRelativeMonitorLocation() throws Exception {
    Client owner = client(), stranger = client();
    String documentId = upload(owner);
    String key = Store.id();
    MvcResult first = create(owner, documentId, key);
    assertStatus(202, first);
    String jobId = onlyJobId(documentId);
    String expected = "/api/v1/jobs/" + jobId;
    assertEquals(expected, first.getResponse().getHeader("Location"),
        "202 must expose a relative monitor Location for the created job");

    MvcResult replay = create(owner, documentId, key);            // first response lost
    assertStatus(202, replay);
    assertEquals(expected, replay.getResponse().getHeader("Location"));
    assertEquals(jobId, body(replay).path("id").asText());
    assertEquals(1, count("select count(*) from jobs where document_id = ?", documentId));
    assertEquals(1, audits(documentId, "CREATE_JOB"));

    String location = first.getResponse().getHeader("Location");
    MvcResult monitor = mvc.perform(get(location).session(owner.session())).andReturn();
    assertStatus(200, monitor);
    assertEquals(jobId, body(monitor).path("id").asText());
    assertNoStore(monitor);
    assertStatus(404, mvc.perform(get(location).session(stranger.session())).andReturn()); // locator, not bearer capability
  }

  /** T2 – passes on baseline; kills M1 (document_id <- job.id) and M2. */
  @Test
  void jobBodyFieldsComeFromTheJobRowAndAreNeverCrossMapped() throws Exception {
    Client owner = client();
    String documentId = upload(owner);
    MvcResult created = create(owner, documentId, Store.id());
    assertStatus(202, created);
    Map<String, Object> row = jdbc.queryForMap(
        "select id, document_id, result_run_id, state from jobs where document_id = ?", documentId);
    String jobId = (String) row.get("id"), runId = (String) row.get("result_run_id");
    assertEquals(3, new HashSet<>(List.of(jobId, documentId, runId)).size(), "oracle needs distinct ids");
    MvcResult polled = mvc.perform(get("/api/v1/jobs/{id}", jobId).session(owner.session())).andReturn();
    assertStatus(200, polled);
    for (MvcResult r : List.of(created, polled)) {
      JsonNode b = body(r);
      assertEquals(jobId, b.path("id").asText(), "id must be the job id");
      assertEquals(documentId, b.path("document_id").asText(), "document_id must be the document, not the job");
      assertEquals(runId, b.path("result_run_id").asText(), "result_run_id must be the preallocated run id");
      assertEquals(row.get("state"), b.path("state").asText());
      assertEquals(12, b.size(), "Job schema unchanged: 12 properties, additionalProperties=false");
      assertNoStore(r);
    }
    assertEquals(0, count("select count(*) from extraction_runs where id = ?", runId),
        "preallocated result_run_id is not evidence that a run exists");
  }

  /** T3 – passes on baseline: key scope, validation boundaries, auth/CSRF, no duplicate rows/audit. */
  @Test
  void idempotencyKeyIsScopedToTheOwnedDocumentAndRetriesNeverDuplicate() throws Exception {
    Client owner = client(), stranger = client();
    String doc1 = upload(owner), doc2 = upload(owner), foreign = upload(stranger);
    String key = Store.id();
    assertStatus(202, create(owner, doc1, key));
    String job1 = onlyJobId(doc1);
    MvcResult replay = create(owner, doc1, key);
    assertStatus(202, replay);
    assertEquals(job1, body(replay).path("id").asText(), "same key + same doc while active = replay, not 409");
    MvcResult other = create(owner, doc2, key);
    assertStatus(202, other);
    assertNotEquals(job1, onlyJobId(doc2), "key scope is (document, key)");
    assertEquals(doc2, body(other).path("document_id").asText());
    MvcResult cross = create(owner, foreign, key);
    assertError(cross, 404, null);
    assertFalse(cross.getResponse().getContentAsString().contains(job1));
    assertError(create(owner, doc1, Store.id()), 409, "ACTIVE_JOB_EXISTS");
    assertError(create(owner, doc1, null), 409, "ACTIVE_JOB_EXISTS");
    assertError(create(owner, doc1, "   "), 409, "ACTIVE_JOB_EXISTS");          // blank == absent
    assertError(create(owner, doc1, "k".repeat(100)), 409, "ACTIVE_JOB_EXISTS"); // valid boundary
    assertError(create(owner, doc1, "k".repeat(101)), 400, "INVALID_IDEMPOTENCY_KEY");
    assertError(create(owner, doc1, "bad/key"), 400, "INVALID_IDEMPOTENCY_KEY");
    assertStatus(403, mvc.perform(post("/api/v1/documents/{id}/jobs", doc1)
        .session(owner.session()).header("Idempotency-Key", Store.id())).andReturn());
    assertStatus(401, mvc.perform(post("/api/v1/documents/{id}/jobs", doc1)
        .with(csrf()).header("Idempotency-Key", Store.id())).andReturn());
    assertEquals(1, count("select count(*) from jobs where document_id = ?", doc1));
    assertEquals(1, count("select count(*) from jobs where document_id = ?", doc2));
    assertEquals(0, count("select count(*) from jobs where document_id = ?", foreign));
    assertEquals(1, audits(doc1, "CREATE_JOB"));
    assertEquals(1, audits(doc2, "CREATE_JOB"));
    assertEquals(0, audits(foreign, "CREATE_JOB"));
  }

  /** T4 – passes on baseline: retryable failure + stale fence + duplicate completion = exactly one run. */
  @Test
  void transientFailureRetryAndStaleCompletionCommitExactlyOneRun() throws Exception {
    Client owner = client();
    String documentId = upload(owner);
    String key = Store.id();
    assertStatus(202, create(owner, documentId, key));
    String jobId = onlyJobId(documentId);
    String runId = jdbc.queryForObject("select result_run_id from jobs where id = ?", String.class, jobId);
    JobService.Claim stale = jobs.claim(jobId);
    assertNotNull(stale);
    assertNull(jobs.claim(jobId), "RUNNING job cannot be claimed twice");
    jobs.fail(stale, "OCR_RUNTIME_ERROR", "synthetic transient failure", true);
    assertEquals("RETRYING", jdbc.queryForObject("select state from jobs where id = ?", String.class, jobId));
    JobService.Claim current = jobs.claim(jobId);
    assertNotNull(current);
    assertNotEquals(stale.token(), current.token());
    assertEquals(runId, current.runId());
    assertFalse(jobs.complete(stale, ai.extract(stale)), "stale lease must be fenced");
    assertTrue(jobs.complete(current, ai.extract(current)));
    assertFalse(jobs.complete(current, ai.extract(current)), "duplicate completion is a no-op");
    assertEquals(runId, jdbc.queryForObject("select id from extraction_runs where job_id = ?", String.class, jobId));
    assertEquals(1, count("select count(*) from extraction_runs where document_id = ?", documentId));
    assertEquals(1, count("select count(*) from revisions where document_id = ?", documentId));
    assertEquals(1, audits(documentId, "CREATE_JOB"));
    assertEquals(1, audits(documentId, "JOB_ERROR"));
    assertEquals(1, audits(documentId, "JOB_COMPLETED"));
    JsonNode polled = body(mvc.perform(get("/api/v1/jobs/{id}", jobId).session(owner.session())).andReturn());
    assertEquals("SUCCEEDED", polled.path("state").asText());
    assertEquals(2, polled.path("attempts").asInt());
    assertEquals(runId, polled.path("result_run_id").asText());
    MvcResult replay = create(owner, documentId, key);
    assertStatus(202, replay);
    assertEquals(jobId, body(replay).path("id").asText(), "keyed replay after success = same job");
    assertEquals(1, count("select count(*) from jobs where document_id = ?", documentId));
    // Characterises a residual risk: a retry without a key after completion is a NEW job.
    assertStatus(202, create(owner, documentId, null));
    assertEquals(2, count("select count(*) from jobs where document_id = ?", documentId));
  }
}
```

| Test | Baseline | After patch | M1 (`document_id`←`job.id`) | M2 (`id`←`resultRunId`) | M4 (`Location`←`documentId`) |
|---|---|---|---|---|---|
| T1 | **Fails: `Location` null** | Passes | Passes | Fails | Fails |
| T2 | Passes | Passes | **Fails** | Fails | Passes |
| T3 | Passes | Passes | Fails (`doc2` check) | Fails | Passes |
| T4 | Passes | Passes | Passes | Fails | Passes |

These mutant columns are predictions; they need an actual run.

## 4. Equivalence partitions (20; negative cases marked †)

| # | Input partition | Expected | Covered by |
|---|---|---|---|
| 1† | No session | 401 `UNAUTHENTICATED`, no job | T3 |
| 2† | Session, no CSRF token | 403, no job | T3 |
| 3 | Own doc, no active job, new key | 202 + `Location`, 1 row, 1 `CREATE_JOB` | T1, T2 |
| 4 | Same key, same doc, job active | 202, same id/`Location`, no new row/audit | T1, T3 |
| 5 | Same key after `SUCCEEDED` | 202, same terminal job | T4 |
| 6 | Same key on another owned doc | New independent job | T3 |
| 7† | Same key on a foreign doc | 404, no job, no id leak | T3 |
| 8† | Different key while active | 409 `ACTIVE_JOB_EXISTS` | T3 (service level: retained test) |
| 9† | Blank or absent key while active | 409 (blank counts as absent) | T3 |
| 10 | Key of exactly 100 chars | Accepted by validation (then 409) | T3 |
| 11† | Key of 101 chars, or key with `/` | 400 `INVALID_IDEMPOTENCY_KEY` | T3 |
| 12 | No key after terminal state | New job (rerun risk) | T4 |
| 13† | User already has 5 active jobs | 429 `JOB_LIMIT` | Retained `WorkflowIntegrationTest.java:557` |
| 14† | GET via `Location` by another user | 404 | T1 |
| 15† | Second claim while RUNNING | `null` | T4 |
| 16 | Retryable failure | RETRYING → reclaim with new token, same `runId` | T4 |
| 17† | Completion with stale token | `false`, no run | T4; retained `:384` |
| 18† | Duplicate completion | `false` | T4; retained `:122` |
| 19† | Late completion after cancel | `false`, no head revision | Retained `:360` |
| 20 | Response mapping | id ≠ `document_id` ≠ `result_run_id`, all equal to DB row | T2 |

**Retained regression (must stay green):** these existing service-level tests in `WorkflowIntegrationTest`, at lines 122, 247, 360, 384 and 557, plus the CSRF/401 checks at 438. No-store is existing Spring Security behaviour that is now asserted.

**Added behaviour:** only `Location`, on both the first 202 and the keyed replay.

**Added coverage of behaviour that already existed:** everything else in T1–T4. Today the suite has no test that sends POST or GET for jobs over HTTP, and nothing asserts `document_id` or `result_run_id` mapping.

**Still missing after T1–T4 (optional):** the claim-after-deadline branch, the non-retryable `fail` path, and `JobWorker.process` exception mapping (the 503 → retryable rule). The real `JobWorker` is disabled in every test.

## 5. Notification risk

There's no notification sender in the backend. A search of `backend/src/main` for notif, mail, webhook, SSE, WebSocket and `ApplicationEvent` returned 0 matches. The only per-event side effects are:
- `audit_events` rows: `CREATE_JOB`, `JOB_ERROR`, `JOB_COMPLETED`, `CANCEL_JOB`
- `extraction_runs` rows
- the initial revision row
- UI polling every 1800 ms (`app.js:295`)

The "duplicate notification" risk therefore becomes duplicate audit events or completion records. T1, T3 and T4 count those exactly. Report notifications as not applicable, with this evidence; don't invent a notifier.

## 6. Mutation oracle

The expected values must not come from the mapper under test:
- **Expected `document_id`:** from the upload result, which goes through `DocumentService.view`, a different mapper.
- **Expected `id` and `result_run_id`:** from `JdbcTemplate` SQL looked up by document id.

Comparing the HTTP body to `jobs.get(...)`, `jobs.create(...)` or `documents.jobView(...)` would hide M1, because those go through the same mapper. Following the `Location` header adds an end-to-end check that M2 and M4 can't get past.

## 7. 200-worker concurrency harness (opt-in, run after the patch)

**Class setup:** `@Tag("load") @EnabledIfSystemProperty(named="vt030.load", matches="true")`, its own H2 database (`jdbc:h2:mem:vt030load`), worker disabled. Run it explicitly, for example `-Dtest=JobAdmissionLoadHarnessTest -Dvt030.load=true`, and confirm that surefire passes the property through.

**Fixture (not timed):**
- 40 users × 5 documents = 200 clients. That's exactly the per-user cap, so a correct run gets no 429s.
- One `MockHttpSession` per worker: 200 service logins. `MockHttpSession` isn't thread-safe, so don't share sessions.
- A real CSRF token per session from `GET /api/v1/auth/csrf`, sent as `X-CSRF-TOKEN`. Avoid `csrf()` here: that post-processor swaps the shared `CsrfFilter` repository.
- Setup cost: about 240 BCrypt(12) operations. Run them in a parallel setup pool and keep them out of the timing.

**Burst mechanics:**
- `newFixedThreadPool(200)`, a `ready` latch of 200 and a `go` latch of 1.
- Each worker times one `mvc.perform` with `nanoTime`.
- It records `HTTP_<status>` with the error code, or `EXCEPTION:<class>` (any `Throwable` or `ExecutionException`).
- A worker still running when the phase budget (e.g. 60 s) runs out is recorded as `TIMEOUT`, with elapsed time set to the budget.
- Write a CSV of every outcome plus a summary **before** asserting.
- Assert `outcomes.size() == 200`.

**Percentiles:** p50, p95 and p99 use the nearest rank over **all 200 outcomes** (`v[ceil(0.95n)-1]`), never successes only.

**Phases and pass criteria:**
- **H1 – admit:** all 202; 200 distinct job ids; DB has 200 rows and 200 `CREATE_JOB` audits; p95 ≤ 5 s.
- **H2 – replay storm with the same keys:** all 202; same ids and `Location` per client; still 200 rows and 200 audits; report p95.
- **H3 – poll storm via `GET Location`:** all 200; ids match; no-store present; p95 ≤ 5 s.
- **H4 – duplicates in flight:**
  1. Cancel the H1 jobs through the service to free the cap.
  2. Upload one new document per user.
  3. The 5 sessions of each user fire the same new key at that document, all synchronised (200 workers).
  4. Expect all 202, exactly 40 distinct ids with 5 identical per document, and 40 rows.

**Environment to record:** JDK version, core count, OS, H2 version (`H2VERSION()`), Hikari `maximumPoolSize` (default 10), and whether a warm-up was run. Report all 3 JVM runs; don't cherry-pick.

**Limits to state explicitly:**
- MockMvc is in-process: no TCP, Tomcat connector or thread pool, socket I/O or browser.
- H2 in PostgreSQL mode isn't PostgreSQL: locking, MVCC and lock timeouts differ.
- Hikari's 10 connections are what queueing measures.
- There's no AI model or service.
- The p95 covers admission and polling only, not job completion (see item 4 in section 1).
- A TCP harness is blocked from one host by the HTTP login limiter: 15 logins per minute per remote address (`AuthController.java:44`).

## 8. Five material pitfalls

1. **No-store is already present on baseline** via Spring Security's default headers. Don't claim it as red. An explicit no-store would also drop `Pragma` and `Expires`.
2. **The oracle must not depend on the mapper.** If it does, M1 is invisible. Also check that the three ids are distinct before comparing them.
3. **Harness traps:**
   - Running 200 clients as one user gives 5 × 202 + 195 × 429 because of the per-user cap.
   - The HTTP login limiter blocks 200 logins.
   - Shared sessions aren't thread-safe.
   - Shared H2 databases and cached test contexts pollute global counts. Scope every count by document id and claim jobs by explicit id, never via `available()`.
4. **The 5 s p95 scope:** worker throughput and the 180 s deadline make completion p95 infeasible by design. Disclose this as derived from config and code, not measured.
5. **The UI creates a new key on every call** (`api.js:67`). Server idempotency doesn't make UI retries safe end to end, and a retry without a key after completion makes a new job (T4 shows this). Treat it as residual risk for the Web owner.

**Coverage of this review:**
- **Read:** the 6 injected files, `WorkflowIntegrationTest`, both YAML configs, `SecurityConfig`, `pom.xml`, `V1__application.sql`, `Store`, `ErrorHandler`, `AuthController`, `StorageReconciler`, `api.js`, and `app.js` lines 270–329.
- **Grepped only:** `AuthService`, `Entities`, `AiClient`, `Json`.
- **Not read:** `ReviewService`, `ContractValidator`, the contract and demo tests, `specs/`, ADRs, and the parent's three Vt030 drafts.

Nothing was run: no build, test, mutation or load measurement. Every pass/fail state above is a prediction until the parent produces the logs.