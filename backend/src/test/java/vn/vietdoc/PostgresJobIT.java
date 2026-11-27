package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.AdditionalAnswers.delegatesTo;
import static org.mockito.Mockito.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.integration.AiClient;
import vn.vietdoc.job.JobService;
import vn.vietdoc.persistence.Store;

/** Executed only by the dedicated PostgreSQL CI job: mvnw -Dtest=PostgresJobIT test. */
@SpringBootTest(properties = {
    "vietdoc.worker-enabled=false", "vietdoc.mode=demo",
    "vietdoc.pipeline-manifest=fictional-fixtures.v1",
    "vietdoc.storage=./target/pg-test-storage"})
class PostgresJobIT {
  @Autowired DataSource dataSource;
  @Autowired AuthService auth;
  @Autowired DocumentService documents;
  @Autowired JobService jobs;
  @Autowired AiClient ai;
  @Autowired Store store;
  @Autowired PlatformTransactionManager transactions;

  @DynamicPropertySource
  static void database(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", () -> required("VIETDOC_PG_TEST_URL"));
    registry.add("spring.datasource.username", () -> required("VIETDOC_PG_TEST_USER"));
    registry.add("spring.datasource.password", () -> required("VIETDOC_PG_TEST_PASSWORD"));
  }

  @Test
  void cleanFlywayConcurrentClaimAndFencedRecoveryPersistOnPostgres() throws Exception {
    try (var connection = dataSource.getConnection()) {
      assertEquals("PostgreSQL", connection.getMetaData().getDatabaseProductName());
      System.out.println("PG_VERSION=" + connection.getMetaData().getDatabaseProductVersion());
      try (var statement = connection.createStatement();
          var versions = statement.executeQuery(
              "select version from flyway_schema_history where success=true order by installed_rank desc limit 1")) {
        assertTrue(versions.next());
        assertEquals("4", versions.getString(1));
      }
    }
    String username = "pg-owner-" + Store.id();
    auth.seed(username, "integration-password");
    var owner = (AuthService.Identity) auth.login(username, "integration-password").get("user");
    byte[] image = Files.readAllBytes(Path.of("..", "samples", "receipt-demo.png"));
    MockMultipartFile file = new MockMultipartFile("file", "receipt.png", "image/png", image);
    var firstDocument = documents.upload(owner.id(), file, "receipt", Store.id());
    var secondDocument = documents.upload(owner.id(), file, "receipt", Store.id());
    var firstJob = jobs.create(firstDocument.id(), owner.id(), "same-key");
    assertEquals(firstJob.id(), jobs.create(firstDocument.id(), owner.id(), "same-key").id());
    var secondJob = jobs.create(secondDocument.id(), owner.id(), "same-key");
    assertNotEquals(firstJob.id(), secondJob.id());

    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch ready = new CountDownLatch(2), go = new CountDownLatch(1);
    try {
      List<Future<JobService.Claim>> attempts = new ArrayList<>();
      for (int i = 0; i < 2; i++) attempts.add(pool.submit(() -> {
        ready.countDown();
        if (!go.await(10, TimeUnit.SECONDS)) throw new AssertionError("claim barrier timeout");
        return jobs.claim(firstJob.id());
      }));
      assertTrue(ready.await(10, TimeUnit.SECONDS));
      go.countDown();
      List<JobService.Claim> winners = new ArrayList<>();
      for (var attempt : attempts) {
        JobService.Claim claim = attempt.get(15, TimeUnit.SECONDS);
        if (claim != null) winners.add(claim);
      }
      assertEquals(1, winners.size());
      var old = winners.get(0);
      new TransactionTemplate(transactions).execute(status -> {
        store.job(firstJob.id(), true).leaseUntil = Instant.now().minusSeconds(1);
        return null;
      });
      jobs.recover();
      var current = jobs.claim(firstJob.id());
      assertNotNull(current);
      assertNotEquals(old.token(), current.token());
      assertNotEquals(old.attemptId(), current.attemptId());
      assertNotEquals(old.runId(), current.runId());
      assertFalse(jobs.complete(old, ai.extract(old)));
      assertTrue(jobs.complete(current, ai.extract(current)));
      assertEquals("SUCCEEDED", jobs.get(firstJob.id(), owner.id()).state());
      assertEquals(1, documents.runs(firstDocument.id(), owner.id()).items().size());
      assertEquals("QUEUED", jobs.get(secondJob.id(), owner.id()).state());
    } finally {
      go.countDown();
      pool.shutdownNow();
    }
  }

  @Test
  void staleRecoverySelectionCannotTerminateANewFinalClaim() throws Exception {
    String username = "pg-recovery-race-" + Store.id();
    auth.seed(username, "integration-password");
    var owner = (AuthService.Identity) auth.login(username, "integration-password").get("user");
    var file = new MockMultipartFile("file", "receipt.png", "image/png",
        Files.readAllBytes(Path.of("..", "samples", "receipt-demo.png")));
    var document = documents.upload(owner.id(), file, "receipt", Store.id());
    var job = jobs.create(document.id(), owner.id(), Store.id());
    var first = jobs.claim(job.id());
    assertNotNull(first);
    var tx = new TransactionTemplate(transactions);
    tx.execute(status -> {
      var row = store.job(job.id(), true);
      row.deadline = Instant.now().plusSeconds(600);
      row.leaseUntil = Instant.now().minusSeconds(30);
      return null;
    });
    jobs.recover();
    var second = jobs.claim(job.id());
    assertNotNull(second);
    tx.execute(status -> {
      store.job(job.id(), true).leaseUntil = Instant.now().minusSeconds(30);
      return null;
    });

    // Intercept only the point before locking; all queries/locks/refreshes use PostgreSQL.
    var selected = new CountDownLatch(1);
    var resume = new CountDownLatch(1);
    Store slowStore = mock(Store.class, delegatesTo(store));
    doAnswer(call -> {
      selected.countDown();
      assertTrue(resume.await(15, TimeUnit.SECONDS), "replacement claim must finish first");
      return store.locked(document.id());
    }).when(slowStore).locked(document.id());
    var slowRecovery = new JobService(slowStore, null, null, null, null,
        "demo", "fixture", 180, 60, 3, "", "", "", "");
    var pool = Executors.newSingleThreadExecutor();
    try {
      Future<?> slow = pool.submit(() -> new TransactionTemplate(transactions).execute(status -> {
        slowRecovery.recover();
        return null;
      }));
      assertTrue(selected.await(15, TimeUnit.SECONDS), "expired selection must precede replacement");
      jobs.recover();
      var replacement = jobs.claim(job.id());
      assertNotNull(replacement);
      resume.countDown();
      slow.get(15, TimeUnit.SECONDS);
      assertEquals("RUNNING", jobs.get(job.id(), owner.id()).state());
      tx.execute(status -> {
        var row = store.job(job.id(), false);
        assertEquals(3, row.attempts);
        assertEquals(replacement.token(), row.leaseToken);
        assertEquals(job.id(), store.locked(document.id()).activeJobId);
        return null;
      });
      assertFalse(jobs.complete(second, ai.extract(second)));
      assertTrue(jobs.complete(replacement, ai.extract(replacement)));
    } finally {
      resume.countDown();
      pool.shutdownNow();
    }
  }

  @Test
  void databaseRejectsCrossDocumentReferencesAndInvalidVersions() throws Exception {
    String username = "pg-constraints-" + Store.id();
    auth.seed(username, "integration-password");
    var owner = (AuthService.Identity) auth.login(username, "integration-password").get("user");
    byte[] image = Files.readAllBytes(Path.of("..", "samples", "receipt-demo.png"));
    var file = new MockMultipartFile("file", "receipt.png", "image/png", image);
    var first = documents.upload(owner.id(), file, "receipt", Store.id());
    var second = documents.upload(owner.id(), file, "receipt", Store.id());
    var firstJob = jobs.create(first.id(), owner.id(), Store.id());
    var secondJob = jobs.create(second.id(), owner.id(), Store.id());
    var firstClaim = jobs.claim(firstJob.id());
    var secondClaim = jobs.claim(secondJob.id());
    assertTrue(jobs.complete(firstClaim, ai.extract(firstClaim)));
    assertTrue(jobs.complete(secondClaim, ai.extract(secondClaim)));
    String firstHead = documents.get(first.id(), owner.id()).headRevisionId();
    String secondHead = documents.get(second.id(), owner.id()).headRevisionId();
    var active = jobs.create(second.id(), owner.id(), Store.id());

    assertSqlState("23503", "update documents set head_revision_id=? where id=?",
        secondHead, first.id());
    assertSqlState("23503", "update documents set active_job_id=? where id=?",
        active.id(), first.id());
    assertSqlState("23503", "update revisions set parent_id=? where id=?",
        secondHead, firstHead);
    assertSqlState("23503", "update revisions set run_id=? where id=?",
        secondClaim.runId(), firstHead);
    assertSqlState("23514", "update documents set version=0 where id=?", first.id());
    assertSqlState("23514", "update jobs set attempts=-1 where id=?", firstJob.id());
    assertEquals(firstHead, documents.get(first.id(), owner.id()).headRevisionId());
  }

  private void assertSqlState(String expected, String sql, String... values) throws Exception {
    try (var connection = dataSource.getConnection();
        var statement = connection.prepareStatement(sql)) {
      for (int i = 0; i < values.length; i++) statement.setString(i + 1, values[i]);
      SQLException error = assertThrows(SQLException.class, statement::executeUpdate);
      assertEquals(expected, error.getSQLState());
    }
  }

  private static String required(String key) {
    String value = System.getenv(key);
    if (value == null || value.isBlank()) throw new IllegalStateException("Missing " + key);
    return value;
  }
}
