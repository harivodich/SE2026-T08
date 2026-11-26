package vn.vietdoc.contracts;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import vn.vietdoc.common.ApiException;
import vn.vietdoc.common.Json;

class ComputeContractTest {
  private final ObjectMapper mapper = new ObjectMapper();
  private ContractValidator validator;
  private ObjectNode request;
  private ObjectNode response;
  private ObjectNode error;

  @BeforeEach
  void setUp() throws Exception {
    validator = new ContractValidator(new Json(mapper));
    request = fixture("compute-request");
    response = fixture("compute-response");
    error = fixture("compute-error");
  }

  @Test
  void bundledComputeSchemasMatchSharedAuthorityByteForByte() throws Exception {
    for (String name : List.of("compute-request", "compute-response", "compute-error")) {
      byte[] shared = Files.readAllBytes(shared("specs/contracts/" + name + ".schema.json"));
      byte[] bundled = new ClassPathResource("contracts/" + name + ".schema.json")
          .getInputStream().readAllBytes();
      assertArrayEquals(shared, bundled, name);
    }
  }

  @Test
  void sharedFixturesValidateAndRequestRejectsWrongVersionTypeIdsAndBudget() {
    validator.computeRequest(request);
    validator.computeResponse(request, response);
    validator.computeError(request, error);
    assertTrue(response.path("result").path("payload").path("merchant_address").isNull());

    ObjectNode wrongVersion = request.deepCopy();
    wrongVersion.put("contract_version", 2);
    assertInvalid(() -> validator.computeRequest(wrongVersion));
    ObjectNode wrongId = request.deepCopy();
    wrongId.put("job_id", "bad");
    assertInvalid(() -> validator.computeRequest(wrongId));
    ObjectNode wrongType = request.deepCopy();
    wrongType.put("schema_version", "invoice.v1");
    assertInvalid(() -> validator.computeRequest(wrongType));
    ObjectNode noBudget = request.deepCopy();
    noBudget.put("remaining_budget_ms", 0);
    assertInvalid(() -> validator.computeRequest(noBudget));
    ObjectNode unknown = request.deepCopy();
    unknown.put("extra", true);
    assertInvalid(() -> validator.computeRequest(unknown));
  }

  @Test
  void computeNumbersUseSchemaValueEquality() {
    request.put("contract_version", 1.0);
    request.put("remaining_budget_ms", 1000.0);
    response.put("contract_version", 1.0);
    error.put("contract_version", 1.0);
    validator.computeRequest(request);
    validator.computeResponse(request, response);
    validator.computeError(request, error);

    request.put("remaining_budget_ms", 1000.5);
    assertInvalid(() -> validator.computeRequest(request));
    request.put("remaining_budget_ms", "1000");
    assertInvalid(() -> validator.computeRequest(request));
  }

  @Test
  void computeDigestsRejectTrailingLineBreaks() {
    for (String ending : List.of("\r", "\n")) {
      String invalidHash = "0".repeat(64) + ending;
      ObjectNode badRequest = request.deepCopy();
      badRequest.put("input_sha256", invalidHash);
      assertInvalid(() -> validator.computeRequest(badRequest));

      ObjectNode badPage = response.deepCopy();
      ((ObjectNode) badPage.path("canonical_page")).put("sha256", invalidHash);
      ((ObjectNode) badPage.path("artifacts").get(0)).put("sha256", invalidHash);
      assertInvalid(() -> validator.computeResponse(request, badPage));

      ObjectNode badArtifact = response.deepCopy();
      ((ObjectNode) badArtifact.path("artifacts").get(1)).put("sha256", invalidHash);
      assertInvalid(() -> validator.computeResponse(request, badArtifact));
    }
  }

  @Test
  void recordedNativeReceiptInvoicePartialEnvelopesValidateAcrossLanguages() throws Exception {
    JsonNode packet = mapper.readTree(Files.readString(shared("tests/contract/native-compute-v2.json")));
    assertEquals(3, packet.path("cases").size());
    int partial = 0;
    for (JsonNode item : packet.path("cases")) {
      validator.computeResponse(item.path("request"), item.path("response"));
      assertEquals(200, item.path("status").asInt());
      if (item.path("recognition_status").asText().equals("partial")) {
        partial++;
        assertTrue(item.path("readable_blocks").asInt() > 0);
        assertTrue(item.path("unreadable_regions").asInt() > 0);
        assertTrue(java.util.stream.StreamSupport.stream(
                item.path("response").path("result").path("issues").spliterator(), false)
            .anyMatch(issue -> issue.path("code").asText().equals("OCR_UNREADABLE_REGIONS")));
      }
    }
    assertEquals(2, partial);
  }

  @Test
  void documentIssueScopeDoesNotAuthorizeAnInvalidFieldPointer() {
    ObjectNode issue = ((ArrayNode) response.path("result").path("issues")).addObject();
    issue.put("id", "OCR_UNREADABLE_REGIONS:/");
    issue.put("code", "OCR_UNREADABLE_REGIONS");
    issue.put("severity", "warning");
    issue.putArray("paths").add("/");
    issue.put("message", "Source contains an unreadable region.");
    validator.computeResponse(request, response);
    assertInvalid(() -> validator.pointer(response.path("result").path("payload"), "/"));
    issue.putArray("paths").add("/not_a_field");
    assertInvalid(() -> validator.computeResponse(request, response));
  }

  @Test
  void responseRejectsCorrelationProvenanceGeometryAndDecimalViolations() {
    ObjectNode wrongAttempt = response.deepCopy();
    wrongAttempt.put("attempt_id", "44444444-4444-4444-8444-444444444444");
    assertInvalid(() -> validator.computeResponse(request, wrongAttempt));
    ObjectNode wrongRun = response.deepCopy();
    ((ObjectNode) wrongRun.path("result")).put("run_id", "44444444-4444-4444-8444-444444444444");
    assertInvalid(() -> validator.computeResponse(request, wrongRun));
    ObjectNode wrongManifest = response.deepCopy();
    ((ObjectNode) wrongManifest.path("result").path("provenance"))
        .put("pipeline_manifest_id", "another.v1");
    assertInvalid(() -> validator.computeResponse(request, wrongManifest));
    ObjectNode tooManyPixels = response.deepCopy();
    ((ObjectNode) tooManyPixels.path("canonical_page")).put("width", 20_000_000);
    assertInvalid(() -> validator.computeResponse(request, tooManyPixels));
    ObjectNode numericMoney = response.deepCopy();
    ((ObjectNode) numericMoney.path("result").path("payload")).put("total_amount", 45000.0);
    assertInvalid(() -> validator.computeResponse(request, numericMoney));
  }

  @Test
  void responseRejectsMutableOrUncorrelatedArtifactDeclarations() {
    ObjectNode duplicate = response.deepCopy();
    ((ObjectNode) duplicate.path("artifacts").get(1))
        .put("asset_key", duplicate.path("artifacts").get(0).path("asset_key").asText());
    assertInvalid(() -> validator.computeResponse(request, duplicate));
    ObjectNode foreignAttempt = response.deepCopy();
    ((ObjectNode) foreignAttempt.path("canonical_page"))
        .put("asset_key", "attempts/11111111-1111-4111-8111-111111111111/44444444-4444-4444-8444-444444444444/canonical.png");
    ((ObjectNode) foreignAttempt.path("artifacts").get(0))
        .put("asset_key", foreignAttempt.path("canonical_page").path("asset_key").asText());
    assertInvalid(() -> validator.computeResponse(request, foreignAttempt));
    ObjectNode traversal = response.deepCopy();
    String key = "attempts/11111111-1111-4111-8111-111111111111/33333333-3333-4333-8333-333333333333/../canonical.png";
    ((ObjectNode) traversal.path("canonical_page")).put("asset_key", key);
    ((ObjectNode) traversal.path("artifacts").get(0)).put("asset_key", key);
    assertInvalid(() -> validator.computeResponse(request, traversal));
    ObjectNode wrongHash = response.deepCopy();
    ((ObjectNode) wrongHash.path("canonical_page"))
        .put("sha256", "1111111111111111111111111111111111111111111111111111111111111111");
    assertInvalid(() -> validator.computeResponse(request, wrongHash));
  }

  @Test
  void errorAllowsUnparsedAttemptButRejectsWrongAttemptAndShape() {
    ObjectNode unparsed = error.deepCopy();
    unparsed.putNull("attempt_id");
    validator.computeError(request, unparsed);
    ObjectNode wrongId = error.deepCopy();
    wrongId.put("attempt_id", "44444444-4444-4444-8444-444444444444");
    assertInvalid(() -> validator.computeError(request, wrongId));
    ObjectNode wrongCode = error.deepCopy();
    wrongCode.put("code", "UNKNOWN");
    assertInvalid(() -> validator.computeError(request, wrongCode));
    ObjectNode wrongRetryable = error.deepCopy();
    wrongRetryable.put("retryable", "true");
    assertInvalid(() -> validator.computeError(request, wrongRetryable));
  }

  private ObjectNode fixture(String name) throws Exception {
    return (ObjectNode) mapper.readTree(Files.readString(shared("tests/contract/" + name + ".json")));
  }

  private Path shared(String path) {
    Path fromRoot = Path.of(path);
    return Files.exists(fromRoot) ? fromRoot : Path.of("..").resolve(path);
  }

  private void assertInvalid(Runnable action) {
    assertThrows(ApiException.class, action::run);
  }
}
