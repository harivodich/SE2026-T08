package vn.vietdoc.integration;

import com.fasterxml.jackson.core.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.io.IOException;
import java.nio.file.Files;
import java.net.http.HttpClient;
import java.time.Instant;
import java.time.Duration;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.*;
import org.springframework.http.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.ResourceAccessException;
import vn.vietdoc.common.*;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.document.PrivateStorage;
import vn.vietdoc.job.JobService.Claim;

@Component
public class AiClient {
  private final Json json;
  private final ContractValidator validator;
  private final PrivateStorage storage;
  private final String endpoint, token;
  private final HttpClient httpClient =
      HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
  private static final int MAX_SUCCESS_BYTES = 2 * 1024 * 1024;
  private static final int MAX_ERROR_BYTES = 16 * 1024;
  private static final ObjectMapper RESPONSE_MAPPER =
      new ObjectMapper(
          JsonFactory.builder()
              .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
              .streamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(32).build())
              .build());

  public AiClient(
      Json json,
      ContractValidator validator,
      PrivateStorage storage,
      @Value("${vietdoc.worker-url}") String endpoint,
      @Value("${vietdoc.worker-token}") String token) {
    this.json = json;
    this.validator = validator;
    this.storage = storage;
    this.endpoint = endpoint;
    this.token = token;
  }

  public JsonNode extract(Claim claim) throws Exception {
    if (claim.mode().equals("http"))
      throw new IllegalStateException("HTTP compute requires verified asset promotion");
    JsonNode payload = validator.empty(claim.type());
    boolean fixture = false;
    if (claim.mode().equals("demo")) {
      JsonNode manifest =
          json.mapper.readTree(new ClassPathResource("fixtures/manifest.json").getInputStream());
      JsonNode entry = manifest.path(claim.hash());
      if (entry.path("document_type").asText().equals(claim.type())) {
        payload = entry.get("payload");
        fixture = true;
      }
    }
    ObjectNode result = json.mapper.createObjectNode();
    result.put("run_id", claim.runId());
    result.put("job_id", claim.id());
    result.put("document_type", claim.type());
    result.put("schema_version", claim.type() + ".v1");
    result.put("language", "vi");
    result.set("payload", payload);
    result.putArray("field_metadata");
    ArrayNode issues = result.putArray("issues");
    validator.add(
        issues,
        fixture ? "DEMO_FIXTURE" : "MANUAL_ENTRY",
        "info",
        "/items",
        fixture
            ? "Dữ liệu từ mẫu giả đã biết; đây không phải kết quả OCR/model thật."
            : "Chưa có kết quả AI cho file này. Nhập dữ liệu bằng cách đối chiếu ảnh nguồn.");
    ObjectNode provenance = result.putObject("provenance");
    provenance.put("pipeline_manifest_id", claim.manifest());
    provenance.put("ocr_version", "unavailable");
    provenance.put("extractor_release_id", fixture ? "fictional-fixture.v1" : "manual.v1");
    provenance.put("normalizer_version", "business.v1");
    return result;
  }

  /** Validated HTTP envelope; the caller must promote assets before DB completion. */
  public JsonNode compute(Claim claim) throws IOException {
    if (token.isBlank())
      throw new ApiException(502, "AI_CONFIGURATION", "Chưa cấu hình service credential.");
    long budget = Duration.between(Instant.now(), claim.deadline()).toMillis();
    if (budget <= 0)
      throw new ApiException(504, "DEADLINE_EXCEEDED", "Job đã hết thời gian xử lý.");
    byte[] original;
    try (var source = Files.newInputStream(storage.original(claim.documentId()))) {
      original = source.readNBytes(20 * 1024 * 1024 + 1);
    }
    if (original.length == 0 || original.length > 20L * 1024 * 1024
        || !Json.sha256(original).equals(claim.hash()))
      throw new ApiException(422, "INPUT_INVALID", "File nguồn không khớp hash đã lưu.");
    budget = Math.min(Duration.between(Instant.now(), claim.deadline()).toMillis(), 180_000);
    if (budget <= 0)
      throw new ApiException(504, "DEADLINE_EXCEEDED", "Job đã hết thời gian xử lý.");
    ObjectNode metadata = json.mapper.createObjectNode();
    metadata.put("contract_version", 1);
    metadata.put("job_id", claim.id());
    metadata.put("run_id", claim.runId());
    metadata.put("attempt_id", claim.attemptId());
    metadata.put("document_type", claim.type());
    metadata.put("schema_version", claim.type() + ".v1");
    metadata.put("language", "vi");
    metadata.put("input_sha256", claim.hash());
    metadata.put("pipeline_manifest_id", claim.manifest());
    metadata.put("remaining_budget_ms", Math.max(1, budget));
    validator.computeRequest(metadata);
    var request = new LinkedMultiValueMap<String, Object>();
    request.add("request", json.write(metadata));
    request.add("file", new ByteArrayResource(original) {
      @Override public String getFilename() { return "document"; }
    });
    var factory = new JdkClientHttpRequestFactory(httpClient);
    factory.setReadTimeout(Duration.ofMillis(Math.min(budget + 5_000, 185_000)));
    RestClient client = RestClient.builder().requestFactory(factory).build();
    try {
      return client.post().uri(endpoint).contentType(MediaType.MULTIPART_FORM_DATA)
          .headers(h -> h.setBearerAuth(token)).body(request).exchange((req, res) -> {
            int status = res.getStatusCode().value();
            boolean transientGateway = status == 502 || status == 503 || status == 504;
            String retryAfter = res.getHeaders().getFirst("Retry-After");
            int limit = status == 200 ? MAX_SUCCESS_BYTES : MAX_ERROR_BYTES;
            byte[] bytes = res.getBody().readNBytes(limit + 1);
            if (bytes.length > limit) {
              if (transientGateway) throw unavailable(retryAfter);
              throw new ApiException(422, "MODEL_OUTPUT_INVALID", "Compute response vượt giới hạn.");
            }
            JsonNode envelope;
            try (JsonParser parser = RESPONSE_MAPPER.createParser(bytes)) {
              envelope = RESPONSE_MAPPER.readTree(parser);
              if (envelope == null || envelope.isMissingNode() || parser.nextToken() != null)
                throw new JsonParseException(parser, "Trailing JSON");
            } catch (JsonProcessingException e) {
              if (transientGateway) throw unavailable(retryAfter);
              throw new ApiException(422, "MODEL_OUTPUT_INVALID", "Compute response không phải JSON hợp lệ.");
            }
            if (status == 200) {
              validator.computeResponse(metadata, envelope);
              return envelope;
            }
            try {
              validator.computeError(metadata, envelope);
            } catch (ApiException e) {
              if (transientGateway && !isValidProtocolEnvelopeWithWrongAttempt(metadata, envelope))
                throw unavailable(retryAfter);
              throw e;
            }
            throw mappedError(status, envelope.path("code").asText(), retryAfter);
          });
    } catch (ResourceAccessException e) {
      throw new ApiException(503, "AI_UNAVAILABLE", "Không kết nối hoặc đọc được compute service.");
    }
  }

  private ApiException unavailable(String retryAfter) {
    return new ApiException(
        503,
        "AI_UNAVAILABLE",
        "Compute service tạm thời không khả dụng.",
        Map.of("retry_after_seconds", boundedRetryAfter(retryAfter)));
  }

  private boolean isValidProtocolEnvelopeWithWrongAttempt(ObjectNode metadata, JsonNode envelope) {
    if (!envelope.isObject() || !envelope.path("attempt_id").isTextual()) return false;
    String attemptId = envelope.path("attempt_id").asText();
    if (attemptId.equals(metadata.path("attempt_id").asText())) return false;
    ObjectNode probe = metadata.deepCopy();
    probe.put("attempt_id", attemptId);
    try {
      validator.computeError(probe, envelope);
      return true;
    } catch (ApiException invalid) {
      return false;
    }
  }

  private ApiException mappedError(int status, String code, String retryAfter) {
    if (status == 503 && Set.of("AI_BUSY", "AI_NOT_READY").contains(code))
      return new ApiException(503, code, "Compute service đang bận hoặc chưa sẵn sàng.",
          Map.of("retry_after_seconds", boundedRetryAfter(retryAfter)));
    if (status == 504 && code.equals("COMPUTE_TIMEOUT"))
      return new ApiException(504, code, "Compute vượt thời gian còn lại.");
    if ((status == 401 || status == 403) && code.equals("SERVICE_AUTH_FAILED"))
      return new ApiException(502, code, "Service credential không hợp lệ.");
    if (status == 413 && code.equals("INPUT_TOO_LARGE")
        || status == 422 && Set.of("INPUT_INVALID", "PROFILE_EXCEEDED", "MANIFEST_UNAVAILABLE", "OUTPUT_INVALID").contains(code)
        || status == 500 && Set.of("MODEL_OOM", "MODEL_LOAD_FAILED", "INTERNAL_ERROR").contains(code))
      return new ApiException(422, code, "Compute từ chối hoặc không xử lý được yêu cầu.");
    return new ApiException(422, "MODEL_OUTPUT_INVALID", "Compute trả status/code không khớp protocol.");
  }

  private int boundedRetryAfter(String value) {
    if (value == null || value.isBlank()) return 0;
    try {
      long seconds = Long.parseLong(value.trim());
      return (int) Math.max(0, Math.min(seconds, 30));
    } catch (NumberFormatException ignored) {
      try {
        long seconds = Duration.between(Instant.now(),
            ZonedDateTime.parse(value.trim(), DateTimeFormatter.RFC_1123_DATE_TIME).toInstant()).getSeconds();
        return (int) Math.max(0, Math.min(seconds + 1, 30));
      } catch (RuntimeException invalid) { return 0; }
    }
  }
}
