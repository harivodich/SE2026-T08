package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
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
        assertEquals("2", versions.getString(1));
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

  private static String required(String key) {
    String value = System.getenv(key);
    if (value == null || value.isBlank()) throw new IllegalStateException("Missing " + key);
    return value;
  }
}
