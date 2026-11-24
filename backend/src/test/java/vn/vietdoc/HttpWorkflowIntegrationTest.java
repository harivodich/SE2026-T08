package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.common.Json;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.contracts.Requests;
import vn.vietdoc.document.ArtifactPromoter;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.document.PrivateStorage;
import vn.vietdoc.document.StorageReconciler;
import vn.vietdoc.integration.AiClient;
import vn.vietdoc.export.ExportService;
import vn.vietdoc.job.JobService;
import vn.vietdoc.persistence.Store;
import vn.vietdoc.review.ReviewService;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:httpflow;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
    "vietdoc.worker-enabled=false", "vietdoc.mode=http", "vietdoc.pipeline-manifest=pilot.v1",
    "vietdoc.worker-token=test-worker-secret"})
class HttpWorkflowIntegrationTest {
  private static final Path ROOT = temporaryRoot();
  @Autowired AuthService auth;
  @Autowired DocumentService documents;
  @Autowired JobService jobs;
  @Autowired PrivateStorage storage;
  @Autowired ArtifactPromoter promoter;
  @Autowired ContractValidator validator;
  @Autowired Json json;
  @Autowired ReviewService review;
  @Autowired ExportService exports;
  @Autowired StorageReconciler reconciler;

  @DynamicPropertySource
  static void paths(DynamicPropertyRegistry registry) {
    registry.add("vietdoc.attempts-root", () -> ROOT.resolve("attempts").toString());
    registry.add("vietdoc.storage", () -> ROOT.resolve("storage").toString());
  }

  @ParameterizedTest
  @ValueSource(strings = {"receipt", "invoice"})
  void fakeHttpComputePromotesCanonicalBeforeCompletionAndKeepsViewerImmutable(String type) throws Exception {
    String username = "http-owner-" + Store.id();
    auth.seed(username, "integration-password");
    var owner = (AuthService.Identity) auth.login(username, "integration-password").get("user");
    var file = new MockMultipartFile("file", type + ".png", "image/png",
        Files.readAllBytes(Path.of("..", "samples", type + "-demo.png")));
    var document = documents.upload(owner.id(), file, type, Store.id());
    var job = jobs.create(document.id(), owner.id(), Store.id());
    var claim = jobs.claim(job.id());
    assertNotNull(claim);
    byte[] canonicalBytes = documents.page(document.id(), owner.id());
    byte[] ocrBytes = ("{\"page\":0,\"width\":" + document.imageWidth()
        + ",\"height\":" + document.imageHeight() + ",\"blocks\":[]}")
        .getBytes(StandardCharsets.UTF_8);
    Path attempt = ROOT.resolve("attempts").resolve(claim.id()).resolve(claim.attemptId());
    Files.createDirectories(attempt);
    Files.write(attempt.resolve("canonical.png"), canonicalBytes);
    Files.write(attempt.resolve("ocr.json"), ocrBytes);
    ObjectNode response = (ObjectNode) json.mapper.readTree(
        Files.readString(Path.of("..", "tests", "contract", "compute-response.json")));
    response.put("attempt_id", claim.attemptId());
    var result = (ObjectNode) response.path("result");
    result.put("job_id", claim.id());
    result.put("run_id", claim.runId());
    result.put("document_type", type);
    result.put("schema_version", type + ".v1");
    if (type.equals("invoice")) {
      var payload = (ObjectNode) validator.empty(type);
      payload.put("total_amount", "80000");
      result.set("payload", payload);
    }
    ((ObjectNode) result.path("provenance")).put("pipeline_manifest_id", claim.manifest());
    String prefix = "attempts/" + claim.id() + "/" + claim.attemptId() + "/";
    var page = (ObjectNode) response.path("canonical_page");
    page.put("asset_key", prefix + "canonical.png");
    page.put("sha256", Json.sha256(canonicalBytes));
    page.put("width", document.imageWidth());
    page.put("height", document.imageHeight());
    var canonical = (ObjectNode) response.path("artifacts").get(0);
    canonical.put("asset_key", prefix + "canonical.png");
    canonical.put("sha256", Json.sha256(canonicalBytes));
    canonical.put("size_bytes", canonicalBytes.length);
    var ocr = (ObjectNode) response.path("artifacts").get(1);
    ocr.put("asset_key", prefix + "ocr.json");
    ocr.put("sha256", Json.sha256(ocrBytes));
    ocr.put("size_bytes", ocrBytes.length);
    validator.computeResponse(request(claim), response);

    var received = new AtomicReference<String>();
    var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext("/internal/v1/compute", exchange -> {
      received.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.ISO_8859_1));
      byte[] bytes = json.write(response).getBytes(StandardCharsets.UTF_8);
      exchange.getResponseHeaders().set("Content-Type", "application/json");
      exchange.sendResponseHeaders(200, bytes.length);
      exchange.getResponseBody().write(bytes);
      exchange.close();
    });
    server.start();
    try {
      var client = new AiClient(json, validator, storage,
          "http://127.0.0.1:" + server.getAddress().getPort() + "/internal/v1/compute",
          "test-worker-secret");
      var envelope = client.compute(claim);
      assertTrue(received.get().contains(claim.attemptId()));
      var promoted = promoter.promote(claim, envelope);
      assertTrue(jobs.complete(claim, envelope.path("result"), promoted));
      var updated = documents.get(document.id(), owner.id());
      assertNotNull(updated.head());
      assertArrayEquals(canonicalBytes, documents.page(document.id(), owner.id()));
      assertArrayEquals(canonicalBytes, documents.page(document.id(), owner.id(), updated.headRevisionId()));
      Files.write(attempt.resolve("canonical.png"), new byte[] {1, 2, 3});
      assertArrayEquals(canonicalBytes, documents.page(document.id(), owner.id()));
      assertFalse(jobs.complete(claim, envelope.path("result"), promoted));

      var editedPayload = updated.head().payload().deepCopy();
      ((ObjectNode) editedPayload).put("total_amount", "81000");
      List<String> rowIds = new ArrayList<>();
      updated.head().rowIds().forEach(value -> rowIds.add(value.asText()));
      var saved = review.save(document.id(), owner.id(), new Requests.Save(
          updated.headRevisionId(), updated.version(), editedPayload,
          "Đối chiếu ảnh canonical", rowIds, List.of("/total_amount")));
      List<String> warnings = new ArrayList<>();
      saved.head().issues().forEach(issue -> {
        if (issue.path("severity").asText().equals("warning")) warnings.add(issue.path("id").asText());
      });
      var approved = review.approve(document.id(), owner.id(), new Requests.Approve(
          saved.headRevisionId(), saved.version(), true, warnings, "Đã đối chiếu"));
      var export = exports.create(document.id(), owner.id(),
          new Requests.Export(approved.headRevisionId(), "json"));
      byte[] approvedBytes = exports.download(export.id(), owner.id());
      assertEquals(export.sha256(), Json.sha256(approvedBytes));
      var laterPayload = approved.head().payload().deepCopy();
      ((ObjectNode) laterPayload).put("total_amount", "82000");
      review.save(document.id(), owner.id(), new Requests.Save(
          approved.headRevisionId(), approved.version(), laterPayload,
          "Bản sửa mới", rowIds, List.of("/total_amount")));
      assertArrayEquals(approvedBytes, exports.download(export.id(), owner.id()));
      assertArrayEquals(canonicalBytes, documents.page(document.id(), owner.id(), approved.headRevisionId()));
    } finally { server.stop(0); }
  }

  private ObjectNode request(JobService.Claim claim) {
    var request = json.mapper.createObjectNode();
    request.put("contract_version", 1);
    request.put("job_id", claim.id());
    request.put("run_id", claim.runId());
    request.put("attempt_id", claim.attemptId());
    request.put("document_type", claim.type());
    request.put("schema_version", claim.type() + ".v1");
    request.put("language", "vi");
    request.put("input_sha256", claim.hash());
    request.put("pipeline_manifest_id", claim.manifest());
    request.put("remaining_budget_ms", 60_000);
    return request;
  }

  @Test
  void orphanInventoryIsDryRunAndNeverDeletesCommittedStorage() throws Exception {
    String runId = Store.id();
    Path orphan = ROOT.resolve("storage").resolve("promoted").resolve(runId);
    Files.createDirectories(orphan);
    Files.writeString(orphan.resolve("promotion.properties"), "run_id=" + runId + "\n");
    var report = reconciler.orphanPromotions(500, Duration.ZERO);
    assertTrue(report.stream().anyMatch(entry -> entry.runId().equals(runId) && entry.hasManifest()));
    assertTrue(Files.exists(orphan.resolve("promotion.properties")));
  }

  private static Path temporaryRoot() {
    try {
      Path root = Files.createTempDirectory(Path.of("target"), "http-flow-");
      Files.createDirectories(root.resolve("attempts"));
      return root;
    } catch (Exception e) { throw new IllegalStateException(e); }
  }
}
