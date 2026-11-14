package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.*;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.persistence.Store;
import vn.vietdoc.persistence.Entities.Document;

/** Real loopback HTTP/session/SQL experiment; deliberately opt-in, not a CI timing test. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
    "spring.datasource.url=jdbc:h2:mem:vt029load;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
    "vietdoc.worker-enabled=false", "vietdoc.mode=manual", "vietdoc.storage=./target/vt029-load-storage"})
@EnabledIfSystemProperty(named = "vt029.load", matches = "true")
class DocumentSearchLoadTest {
  @LocalServerPort int port;
  @Autowired ObjectMapper mapper;
  @Autowired AuthService auth;
  @Autowired Store store;
  @Autowired PlatformTransactionManager tm;

  @Test void tc13_eightyConcurrentHttpTasks() throws Exception {
    String username = "load-" + UUID.randomUUID();
    String password = "vt029-fictional-password";
    auth.seed(username, password);
    String owner = ((AuthService.Identity) auth.login(username, password).get("user")).id();
    List<String> expected = new ArrayList<>();
    new TransactionTemplate(tm).executeWithoutResult(tx -> {
      for (int i = 0; i < 240; i++) {
        Document d = new Document(); d.id = String.format("%036d", i);
        d.ownerId = owner; d.filename = i % 2 == 0 ? "Hóa đơn mẫu.png" : "Biên lai.png";
        d.documentType = i % 2 == 0 ? "invoice" : "receipt";
        d.contentType = "image/png"; d.fileHash = "0".repeat(64); d.fileBytes = 128;
        d.imageWidth = 10; d.imageHeight = 10; d.version = 1;
        d.createdAt = Instant.parse("2026-01-02T03:04:05Z"); store.em().persist(d);
        if (i % 2 == 0) expected.add(d.id);
      }
    });
    expected.sort(Comparator.reverseOrder());
    List<String> expectedPage = List.copyOf(expected.subList(0, 20));
    CookieManager cookies = new CookieManager(null, CookiePolicy.ACCEPT_ALL);
    HttpClient client = HttpClient.newBuilder().cookieHandler(cookies)
        .connectTimeout(Duration.ofSeconds(5)).build();
      String base = "http://127.0.0.1:" + port + "/api/v1";
      var csrf = client.send(HttpRequest.newBuilder(URI.create(base + "/auth/csrf")).GET().build(),
          HttpResponse.BodyHandlers.ofString());
      assertEquals(200, csrf.statusCode());
      var login = client.send(HttpRequest.newBuilder(URI.create(base + "/auth/session"))
          .header("Content-Type", "application/json")
          .header("X-CSRF-TOKEN", mapper.readTree(csrf.body()).path("token").asText())
          .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(
              Map.of("username", username, "password", password)))).build(), HttpResponse.BodyHandlers.ofString());
      assertEquals(200, login.statusCode());
      var request = HttpRequest.newBuilder(URI.create(base + "/documents?q="
          + URLEncoder.encode("HÓA", java.nio.charset.StandardCharsets.UTF_8)
          + "&type=invoice&limit=20")).timeout(Duration.ofSeconds(30)).GET().build();
      for (int i = 0; i < 10; i++) verify(client.send(request, HttpResponse.BodyHandlers.ofString()), expectedPage);
      List<Double> durations = new ArrayList<>(); int failures = 0;
      ExecutorService pool = Executors.newFixedThreadPool(80);
      try {
        for (int wave = 0; wave < 3; wave++) {
          CountDownLatch ready = new CountDownLatch(80), start = new CountDownLatch(1);
          List<Future<Double>> futures = new ArrayList<>();
          for (int i = 0; i < 80; i++) futures.add(pool.submit(() -> {
            ready.countDown(); assertTrue(start.await(15, TimeUnit.SECONDS));
            long begin = System.nanoTime();
            verify(client.send(request, HttpResponse.BodyHandlers.ofString()), expectedPage);
            return (System.nanoTime() - begin) / 1_000_000.0;
          }));
          assertTrue(ready.await(15, TimeUnit.SECONDS)); start.countDown();
          for (Future<Double> future : futures) {
            try { durations.add(future.get(40, TimeUnit.SECONDS)); }
            catch (ExecutionException | TimeoutException e) { failures++; }
          }
        }
      } finally { pool.shutdownNow(); }
      Collections.sort(durations);
      Double p95 = durations.isEmpty() ? null : durations.get((int) Math.ceil(durations.size() * .95) - 1);
      Map<String, Object> result = new LinkedHashMap<>();
      result.put("timestamp_utc", Instant.now().toString()); result.put("concurrency", 80);
      result.put("waves", 3); result.put("warmup", 10); result.put("dataset_rows", 240);
      result.put("successes", durations.size()); result.put("failures", failures);
      result.put("p95_ms", p95); result.put("target_ms", 2500);
      result.put("target_met", failures == 0 && p95 != null && p95 <= 2500);
      result.put("latencies_ms", durations); result.put("jdk", System.getProperty("java.version"));
      result.put("os", System.getProperty("os.name") + " " + System.getProperty("os.arch"));
      result.put("processors", Runtime.getRuntime().availableProcessors());
      result.put("database", "H2 in-memory, Flyway V1; not PostgreSQL");
      result.put("scope", "1 authenticated session, loopback HTTP, fixed first page, no OCR/browser");
      Files.writeString(Path.of("target/vt029-load.json"), mapper.writerWithDefaultPrettyPrinter().writeValueAsString(result));
      assertEquals(0, failures, "All 240 responses must be correct; inspect target/vt029-load.json");
      assertEquals(240, durations.size());
      // Target is reported, not asserted: avoid environment-sensitive correctness tests.
      System.out.println("VT029_LOAD p95_ms=" + p95 + " target_met=" + result.get("target_met"));
  }
  void verify(HttpResponse<String> response, List<String> expected) throws Exception {
    assertEquals(200, response.statusCode()); JsonNode body = mapper.readTree(response.body());
    List<String> actual = new ArrayList<>(); body.path("items").forEach(x -> {
      assertEquals("invoice", x.path("document_type").asText()); actual.add(x.path("id").asText());
    });
    assertEquals(expected, actual); assertEquals(expected.get(19), body.path("next_cursor").asText());
  }
}
