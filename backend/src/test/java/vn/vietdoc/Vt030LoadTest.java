package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import vn.vietdoc.common.Json;
import vn.vietdoc.persistence.Entities.*;
import vn.vietdoc.persistence.Store;

/** 200 synchronized MockMvc clients, real H2 transactions; NOT TCP/production/GPU load. */
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:vt030load;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=20000",
    "spring.datasource.hikari.maximum-pool-size=10", "vietdoc.worker-enabled=false",
    "vietdoc.mode=manual", "vietdoc.storage=./target/vt030-load-storage", "logging.level.root=ERROR"
})
@AutoConfigureMockMvc
class Vt030LoadTest {
  @Autowired MockMvc mvc;
  @Autowired Store store;
  @Autowired Json json;
  @Autowired PlatformTransactionManager tm;
  record Fixture(String documentId, MockHttpSession session) {}
  record Outcome(int index, long elapsedNs, int status, String jobId, String error) {}

  Fixture fixture() {
    String userId = Store.id();
    String token = "synthetic-vt030-" + Store.id();
    String docId = Store.id();
    new TransactionTemplate(tm).executeWithoutResult(tx -> {
      UserAccount user = new UserAccount();
      user.id = userId; user.username = "load-" + userId;
      user.passwordHash = "fixture-not-a-login-password"; user.createdAt = Instant.now();
      store.em().persist(user);
      Session session = new Session();
      session.tokenHash = Json.sha256(token); session.userId = userId;
      session.expiresAt = Instant.now().plusSeconds(3600); store.em().persist(session);
      Document doc = new Document();
      doc.id = docId; doc.ownerId = userId; doc.filename = "fictional-load.png";
      doc.documentType = "receipt"; doc.contentType = "image/png";
      doc.fileHash = "0".repeat(64); doc.fileBytes = 1; doc.imageWidth = 1; doc.imageHeight = 1;
      doc.createdAt = Instant.now(); doc.version = 0; store.em().persist(doc);
    });
    MockHttpSession session = new MockHttpSession();
    session.setAttribute("vietdoc-token", token);
    return new Fixture(docId, session);
  }

  @Test
  void tc17TwoHundredIndependentAdmissions() throws Exception {
    List<Fixture> fixtures = new ArrayList<>();
    for (int i = 0; i < 200; i++) fixtures.add(fixture());
    run("200-independent-users", fixtures, false);
  }

  @Test
  void tc18TwoHundredLostResponseRetriesCreateOneJob() throws Exception {
    Fixture fixture = fixture();
    run("200-same-key-retries", Collections.nCopies(200, fixture), true);
  }

  void run(String name, List<Fixture> inputs, boolean duplicate) throws Exception {
    int count = inputs.size();
    CountDownLatch ready = new CountDownLatch(count);
    CountDownLatch start = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(count);
    List<Future<Outcome>> futures = new ArrayList<>();
    String prefix = Store.id();
    List<Outcome> results = new ArrayList<>();
    AtomicInteger inflight = new AtomicInteger();
    AtomicInteger peak = new AtomicInteger();
    try {
      for (int i = 0; i < count; i++) {
        final int index = i;
        futures.add(pool.submit(() -> {
          ready.countDown();
          if (!start.await(30, TimeUnit.SECONDS)) return new Outcome(index, 0, 0, "", "start timeout");
          long begun = System.nanoTime();
          int active = inflight.incrementAndGet();
          peak.accumulateAndGet(active, Math::max);
          try {
            Fixture f = inputs.get(index);
            var response = mvc.perform(post("/api/v1/documents/{id}/jobs", f.documentId())
                .session(f.session()).with(csrf()).header("Idempotency-Key", prefix + (duplicate ? "-same" : "-" + index)))
                .andReturn().getResponse();
            String id = json.read(response.getContentAsString()).path("id").asText();
            return new Outcome(index, System.nanoTime() - begun, response.getStatus(), id, "");
          } catch (Exception e) {
            return new Outcome(index, System.nanoTime() - begun, 0, "", e.getClass().getSimpleName());
          } finally {
            inflight.decrementAndGet();
          }
        }));
      }
      assertTrue(ready.await(30, TimeUnit.SECONDS), "all 200 clients must be parked before release");
      start.countDown();
      long released = System.nanoTime();
      long end = released + TimeUnit.SECONDS.toNanos(60);
      for (int i = 0; i < futures.size(); i++) {
        try {
          results.add(futures.get(i).get(Math.max(1, end - System.nanoTime()), TimeUnit.NANOSECONDS));
        } catch (TimeoutException | ExecutionException e) {
          futures.get(i).cancel(true);
          results.add(new Outcome(i, System.nanoTime() - released, 0, "", e.getClass().getSimpleName()));
        }
      }
    } finally {
      start.countDown(); pool.shutdownNow();
      assertTrue(pool.awaitTermination(15, TimeUnit.SECONDS));
    }
    long[] durations = results.stream().mapToLong(Outcome::elapsedNs).sorted().toArray();
    double p95Ms = durations[(int) Math.ceil(.95 * count) - 1] / 1_000_000.0;
    long failures = results.stream().filter(r -> r.status() != 202 || r.jobId().isBlank() || !r.error().isEmpty()).count();
    Set<String> jobIds = new HashSet<>();
    results.forEach(r -> jobIds.add(r.jobId()));
    long expected = duplicate ? 1 : 200;
    long actualJobs = 0, actualCreateAudits = 0;
    Set<String> documentIds = new HashSet<>();
    inputs.forEach(f -> documentIds.add(f.documentId()));
    for (String id : documentIds) {
      actualJobs += new TransactionTemplate(tm).execute(tx -> store.em()
          .createQuery("select count(j) from Job j where j.documentId=:d", Long.class).setParameter("d", id).getSingleResult());
      actualCreateAudits += new TransactionTemplate(tm).execute(tx -> store.em()
          .createQuery("select count(a) from AuditEvent a where a.documentId=:d and a.action='CREATE_JOB'", Long.class)
          .setParameter("d", id).getSingleResult());
    }
    Map<String,Object> report = new LinkedHashMap<>();
    report.put("scenario", name); report.put("clients", count); report.put("barrier_ready", count);
    report.put("observed_peak_inflight", peak.get());
    report.put("p95_ms", p95Ms); report.put("p95_target_ms", 5000); report.put("errors", failures);
    report.put("unique_job_ids", jobIds.size()); report.put("persisted_jobs", actualJobs);
    report.put("create_audits", actualCreateAudits); report.put("expected_jobs", expected);
    report.put("all_outcomes_in_percentile", true); report.put("outcomes", results);
    report.put("limitations", "MockMvc+H2, seeded synthetic DB/session fixtures, worker disabled; excludes fixture prep, TCP/login/upload/inference/notification delivery");
    Path target = Path.of("target/vt030-results", name + ".json");
    Files.createDirectories(target.getParent()); Files.writeString(target, json.write(report));
    assertEquals(200, results.size()); assertEquals(0, failures, "all errors counted, not dropped");
    assertEquals(expected, jobIds.size()); assertEquals(expected, actualJobs); assertEquals(expected, actualCreateAudits);
    assertTrue(p95Ms <= 5000, "p95 admission <=5000ms in this measured harness only: " + p95Ms);
  }
}
