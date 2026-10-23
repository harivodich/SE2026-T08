package vn.vietdoc.integration;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.*;
import org.springframework.http.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import vn.vietdoc.common.*;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.document.PrivateStorage;
import vn.vietdoc.job.JobService.Claim;

@Component
public class AiClient {
  private final Json json;
  private final ContractValidator validator;
  private final PrivateStorage storage;
  private final RestClient client;
  private final String endpoint, token;

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
    var factory =
        new JdkClientHttpRequestFactory(
            HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build());
    factory.setReadTimeout(Duration.ofSeconds(120));
    this.client = RestClient.builder().requestFactory(factory).build();
  }

  public JsonNode extract(Claim claim) throws Exception {
    if (claim.mode().equals("http")) {
      var request = new LinkedMultiValueMap<String, Object>();
      request.add("file", new FileSystemResource(storage.original(claim.documentId())));
      request.add(
          "request",
          json.write(
              Map.of(
                  "document_id",
                  claim.documentId(),
                  "job_id",
                  claim.id(),
                  "run_id",
                  claim.runId(),
                  "document_type",
                  claim.type(),
                  "schema_version",
                  claim.type() + ".v1",
                  "pipeline_manifest_id",
                  claim.manifest(),
                  "deadline",
                  claim.deadline())));
      return client
          .post()
          .uri(endpoint)
          .contentType(MediaType.MULTIPART_FORM_DATA)
          .headers(
              h -> {
                if (!token.isBlank()) h.setBearerAuth(token);
              })
          .body(request)
          .exchange(
              (req, res) -> {
                if (res.getStatusCode().is5xxServerError())
                  throw new ApiException(503, "AI_UNAVAILABLE", "Dịch vụ AI chưa sẵn sàng.");
                if (!res.getStatusCode().is2xxSuccessful())
                  throw new ApiException(422, "MODEL_OUTPUT_INVALID", "Worker AI từ chối yêu cầu.");
                byte[] bytes = res.getBody().readNBytes(1048577);
                if (bytes.length > 1048576)
                  throw new ApiException(422, "MODEL_OUTPUT_INVALID", "Kết quả AI vượt giới hạn.");
                return json.mapper.readTree(bytes);
              });
    }
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
}
