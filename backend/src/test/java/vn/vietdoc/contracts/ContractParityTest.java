package vn.vietdoc.contracts;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import vn.vietdoc.common.ApiException;
import vn.vietdoc.common.Json;

class ContractParityTest {
  @Test
  void sharedCorpusProducesExpectedAcceptanceAndMachineReadableEvidence() throws Exception {
    var mapper = new ObjectMapper();
    var validator = new ContractValidator(new Json(mapper));
    var corpusPath = Path.of("../tests/contract/parity-cases.json");
    var bytes = Files.readAllBytes(corpusPath);
    var corpus = mapper.readTree(bytes);
    assertEquals(1, corpus.path("version").asInt());
    assertTrue(corpus.path("cases").size() >= 16);
    var outcomes = mapper.createObjectNode();
    for (var test : corpus.path("cases")) {
      var id = test.path("id").asText();
      assertFalse(id.isBlank());
      assertFalse(outcomes.has(id), "duplicate parity case");
      boolean accepted = true;
      try {
        switch (test.path("kind").asText()) {
          case "request" -> validator.computeRequest(test.path("value"));
          case "response" -> validator.computeResponse(corpus.path("request"), test.path("value"));
          case "error" -> validator.computeError(corpus.path("request"), test.path("value"));
          default -> throw new IllegalArgumentException("unknown parity case kind");
        }
      } catch (ApiException error) {
        accepted = false;
      }
      assertEquals(test.path("expected").asBoolean(), accepted, id);
      outcomes.put(id, accepted);
    }
    var report = mapper.createObjectNode();
    report.put("corpus_sha256", Json.sha256(bytes));
    report.set("outcomes", outcomes);
    Files.createDirectories(Path.of("target"));
    Files.writeString(Path.of("target/parity-java.json"), mapper.writeValueAsString(report));
  }
}
