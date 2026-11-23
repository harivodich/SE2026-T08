package vn.vietdoc.integration;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import vn.vietdoc.common.ApiException;
import vn.vietdoc.common.Json;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.document.PrivateStorage;
import vn.vietdoc.job.JobService;

class AiClientTest {
  @TempDir Path temporary;
  private final Json json = new Json(new ObjectMapper());
  private HttpServer server;
  private JobService.Claim claim;
  private AiClient client;
  private ObjectNode success;
  private final AtomicReference<String> received = new AtomicReference<>();
  private final AtomicInteger calls = new AtomicInteger();
  private int status = 200;
  private String retryAfter;
  private byte[] body;

  @BeforeEach
  void setUp() throws Exception {
    JsonNode request = fixture("compute-request");
    byte[] input = "synthetic receipt".getBytes(StandardCharsets.UTF_8);
    String documentId = "55555555-5555-4555-8555-555555555555";
    Path original = temporary.resolve(documentId).resolve("original");
    Files.createDirectories(original.getParent());
    Files.write(original, input);
    claim = new JobService.Claim(
        request.path("job_id").asText(), documentId, request.path("run_id").asText(),
        "66666666-6666-4666-8666-666666666666", request.path("attempt_id").asText(),
        "receipt", Json.sha256(input), "http", request.path("pipeline_manifest_id").asText(),
        Instant.now().plusSeconds(60));
    success = (ObjectNode) fixture("compute-response");
    body = json.write(success).getBytes(StandardCharsets.UTF_8);
    server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext("/internal/v1/compute", exchange -> {
      calls.incrementAndGet();
      received.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.ISO_8859_1));
      exchange.getResponseHeaders().set("Content-Type", "application/json");
      if (retryAfter != null) exchange.getResponseHeaders().set("Retry-After", retryAfter);
      exchange.sendResponseHeaders(status, body.length);
      exchange.getResponseBody().write(body);
      exchange.close();
    });
    server.start();
    client = new AiClient(json, new ContractValidator(json),
        new PrivateStorage(temporary.toString(), 20_000_000),
        "http://127.0.0.1:" + server.getAddress().getPort() + "/internal/v1/compute", "secret");
  }

  @AfterEach
  void stop() { if (server != null) server.stop(0); }

  @Test
  void sendsContractMetadataAndReturnsOnlyExtractionResult() throws Exception {
    JsonNode envelope = client.compute(claim);
    assertEquals(success, envelope);
    String multipart = received.get();
    for (String field : new String[] {"contract_version", "job_id", "run_id", "attempt_id",
        "schema_version", "language", "input_sha256", "pipeline_manifest_id", "remaining_budget_ms"})
      assertTrue(multipart.contains("\"" + field + "\""), field);
    assertTrue(multipart.contains(claim.hash()));
    assertTrue(multipart.contains(claim.attemptId()));
    assertFalse(multipart.contains("\"deadline\""));
    assertEquals(1, calls.get());
  }

  @Test
  void rejectsWrongCorrelationAndProvenance() {
    success.put("attempt_id", "77777777-7777-4777-8777-777777777777");
    body = json.write(success).getBytes(StandardCharsets.UTF_8);
    assertEquals("CONTRACT_INVALID", assertThrows(ApiException.class, () -> client.compute(claim)).code);
    success.put("attempt_id", claim.attemptId());
    ((ObjectNode) success.path("result").path("provenance"))
        .put("pipeline_manifest_id", "other.v1");
    body = json.write(success).getBytes(StandardCharsets.UTF_8);
    assertEquals("CONTRACT_INVALID", assertThrows(ApiException.class, () -> client.compute(claim)).code);
  }

  @Test
  void rejectsMalformedOversizedAndDuplicateJson() {
    body = "{not-json".getBytes(StandardCharsets.UTF_8);
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class, () -> client.compute(claim)).code);
    body = new byte[2 * 1024 * 1024 + 1];
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class, () -> client.compute(claim)).code);
    body = "{\"contract_version\":1,\"contract_version\":1}".getBytes(StandardCharsets.UTF_8);
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class, () -> client.compute(claim)).code);
  }

  @Test
  void mapsBusyAuthTimeoutAndRejectsMismatchedStatusCode() {
    ObjectNode error = (ObjectNode) fixture("compute-error");
    error.put("code", "AI_BUSY");
    status = 503;
    retryAfter = "120";
    body = json.write(error).getBytes(StandardCharsets.UTF_8);
    ApiException busy = assertThrows(ApiException.class, () -> client.compute(claim));
    assertEquals("AI_BUSY", busy.code);
    assertEquals(503, busy.status);
    assertEquals(30, busy.details.get("retry_after_seconds"));

    status = 401;
    error.put("code", "SERVICE_AUTH_FAILED");
    body = json.write(error).getBytes(StandardCharsets.UTF_8);
    assertEquals(502, assertThrows(ApiException.class, () -> client.compute(claim)).status);

    status = 504;
    error.put("code", "COMPUTE_TIMEOUT");
    body = json.write(error).getBytes(StandardCharsets.UTF_8);
    assertEquals(504, assertThrows(ApiException.class, () -> client.compute(claim)).status);

    status = 503;
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class, () -> client.compute(claim)).code);
  }

  @Test
  void expiredJobDoesNotContactCompute() {
    var expired = new JobService.Claim(claim.id(), claim.documentId(), claim.runId(),
        claim.token(), claim.attemptId(), claim.type(), claim.hash(), claim.mode(),
        claim.manifest(), Instant.now().minusSeconds(1));
    assertEquals("DEADLINE_EXCEEDED", assertThrows(ApiException.class, () -> client.compute(expired)).code);
    assertEquals(0, calls.get());
  }

  @Test
  void changedOriginalCannotBeSubmittedWithStoredHash() throws Exception {
    Files.write(temporary.resolve(claim.documentId()).resolve("original"),
        "different receipt".getBytes(StandardCharsets.UTF_8));
    assertEquals("INPUT_INVALID", assertThrows(ApiException.class, () -> client.compute(claim)).code);
    assertEquals(0, calls.get());
  }

  @Test
  void lostResponseIsTransientAndDoesNotExposeNetworkDetails() {
    server.removeContext("/internal/v1/compute");
    server.createContext("/internal/v1/compute", exchange -> exchange.close());
    ApiException failure = assertThrows(ApiException.class, () -> client.compute(claim));
    assertEquals(503, failure.status);
    assertEquals("AI_UNAVAILABLE", failure.code);
    assertFalse(failure.getMessage().contains("127.0.0.1"));
  }

  private JsonNode fixture(String name) {
    try {
      Path path = Path.of("..", "tests", "contract", name + ".json");
      return json.mapper.readTree(Files.readString(path));
    } catch (Exception e) { throw new IllegalStateException(e); }
  }
}
