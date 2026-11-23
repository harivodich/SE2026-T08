package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.common.Json;
import vn.vietdoc.contracts.Requests;
import vn.vietdoc.document.ArtifactPromoter;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.export.ExportService;
import vn.vietdoc.integration.AiClient;
import vn.vietdoc.job.JobService;
import vn.vietdoc.persistence.Store;
import vn.vietdoc.review.ReviewService;

/** Dedicated host-only acceptance harness. Never substitute a fake HTTP server for this test. */
@SpringBootTest(properties = {"vietdoc.worker-enabled=false"})
class ActualProviderIT {
  @Autowired AuthService auth;
  @Autowired DocumentService documents;
  @Autowired JobService jobs;
  @Autowired AiClient ai;
  @Autowired ArtifactPromoter promoter;
  @Autowired ReviewService review;
  @Autowired ExportService exports;
  @Autowired Json json;
  @Autowired DataSource dataSource;

  @DynamicPropertySource
  static void actualRuntime(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", () -> required("VIETDOC_ACTUAL_DB_URL"));
    registry.add("spring.datasource.username", () -> required("VIETDOC_ACTUAL_DB_USER"));
    registry.add("spring.datasource.password", () -> required("VIETDOC_ACTUAL_DB_PASSWORD"));
    registry.add("vietdoc.mode", () -> "http");
    registry.add("vietdoc.pipeline-manifest", () -> required("VIETDOC_ACTUAL_MANIFEST"));
    registry.add("vietdoc.worker-url", () -> required("VIETDOC_ACTUAL_URL"));
    registry.add("vietdoc.worker-token", () -> required("VIETDOC_ACTUAL_TOKEN"));
    registry.add("vietdoc.attempts-root", () -> required("VIETDOC_ACTUAL_ATTEMPTS_ROOT"));
    registry.add("vietdoc.storage", () -> required("VIETDOC_ACTUAL_JAVA_STORAGE"));
  }

  @ParameterizedTest
  @ValueSource(strings = {"receipt", "invoice"})
  void nativeProviderFlowsThroughPostgresReviewAndExport(String type) throws Exception {
    try (var connection = dataSource.getConnection()) {
      assertEquals("PostgreSQL", connection.getMetaData().getDatabaseProductName(),
          "Actual-provider acceptance requires PostgreSQL");
    }
    String manifest = required("VIETDOC_ACTUAL_MANIFEST");
    String digest = required("VIETDOC_ACTUAL_RELEASE_DIGEST");
    String sourceSha = required("VIETDOC_ACTUAL_SOURCE_SHA");
    Process revision = new ProcessBuilder("git", "rev-parse", "HEAD")
        .directory(Path.of("..").toFile()).start();
    String observedSha = new String(revision.getInputStream().readAllBytes()).trim();
    assertEquals(0, revision.waitFor(), "git rev-parse must succeed on the candidate host");
    assertEquals(observedSha, sourceSha, "Candidate source SHA must match the checkout");
    Path releaseManifest = Path.of(required("VIETDOC_ACTUAL_RELEASE_MANIFEST_PATH"));
    assertTrue(Files.isRegularFile(releaseManifest), "Pinned release manifest must be readable");
    byte[] manifestBytes;
    try (var input = Files.newInputStream(releaseManifest)) {
      manifestBytes = input.readNBytes(1024 * 1024 + 1);
    }
    assertTrue(manifestBytes.length <= 1024 * 1024, "Release manifest is unexpectedly large");
    assertEquals(Json.sha256(manifestBytes), digest.replaceFirst("^sha256:", ""),
        "Release digest must match the pinned manifest bytes");
    URI compute = URI.create(required("VIETDOC_ACTUAL_URL"));
    URI ready = compute.resolve("/health/ready");
    HttpResponse<String> health = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build()
        .send(HttpRequest.newBuilder(ready).timeout(Duration.ofSeconds(5)).GET().build(),
            HttpResponse.BodyHandlers.ofString());
    assertEquals(200, health.statusCode(), "AI service must be ready before acceptance");
    JsonNode readiness = json.mapper.readTree(health.body());
    assertEquals("READY", readiness.path("status").asText());
    boolean pinned = false;
    for (JsonNode release : readiness.path("releases")) pinned |= manifest.equals(release.asText());
    assertTrue(pinned, "Pinned manifest missing from provider readiness");

    String username = "actual-owner-" + Store.id();
    auth.seed(username, "integration-password");
    var owner = (AuthService.Identity) auth.login(username, "integration-password").get("user");
    String extension = type.equals("receipt") ? "png" : "pdf";
    Path sample = Path.of("..", "samples", type + "-demo." + extension);
    var file = new MockMultipartFile("file", sample.getFileName().toString(),
        extension.equals("pdf") ? "application/pdf" : "image/png", Files.readAllBytes(sample));
    var document = documents.upload(owner.id(), file, type, Store.id());
    var job = jobs.create(document.id(), owner.id(), Store.id());
    var claim = jobs.claim(job.id());
    assertNotNull(claim);
    JsonNode envelope = ai.compute(claim);
    var promoted = promoter.promote(claim, envelope);
    assertTrue(jobs.complete(claim, envelope.path("result"), promoted));
    assertTrue(documents.page(document.id(), owner.id()).length > 0);
    var current = documents.get(document.id(), owner.id());
    assertNotNull(current.head());
    ObjectNode payload = current.head().payload().deepCopy();
    if (payload.path("total_amount").isNull())
      payload.put("total_amount", type.equals("receipt") ? "45000" : "80000");
    List<String> rowIds = new ArrayList<>();
    current.head().rowIds().forEach(value -> rowIds.add(value.asText()));
    var saved = review.save(document.id(), owner.id(), new Requests.Save(
        current.headRevisionId(), current.version(), payload, "Đối chiếu chứng từ nguồn",
        rowIds, List.of("/total_amount")));
    List<String> warnings = new ArrayList<>();
    saved.head().issues().forEach(issue -> {
      if (issue.path("severity").asText().equals("warning")) warnings.add(issue.path("id").asText());
    });
    var approved = review.approve(document.id(), owner.id(), new Requests.Approve(
        saved.headRevisionId(), saved.version(), true, warnings, "Đối chiếu ảnh nguồn"));
    var exported = exports.create(document.id(), owner.id(),
        new Requests.Export(approved.headRevisionId(), "json"));
    assertEquals(exported.sha256(), Json.sha256(exports.download(exported.id(), owner.id())));
    System.out.println("ACTUAL_PROVIDER type=" + type + " source_sha=" + sourceSha
        + " release_digest=" + digest + " manifest=" + manifest + " run_id=" + claim.runId()
        + " export_sha256=" + exported.sha256());
  }

  private static String required(String key) {
    String value = System.getenv(key);
    if (value == null || value.isBlank()) throw new IllegalStateException("Missing " + key);
    return value;
  }
}
