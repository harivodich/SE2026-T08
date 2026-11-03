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
import vn.vietdoc.common.ApiException;
import vn.vietdoc.common.Json;

class BusinessContractTest {
  private final ObjectMapper mapper = new ObjectMapper();
  private ContractValidator contracts;
  private JsonNode fixture;

  @BeforeEach
  void setUp() throws Exception {
    Json json = new Json(mapper);
    contracts = new ContractValidator(json);
    fixture = mapper.readTree(Files.readString(sharedFixturePath()));
  }

  @Test
  void sharedFixturesCoverBothBusinessDtosAndValidationBoundaries() {
    for (String type : List.of("receipt", "invoice")) {
      ObjectNode base = (ObjectNode) fixture.path("payloads").path(type).deepCopy();
      var dto = contracts.business(type, base);
      assertEquals(
          type.equals("receipt") ? BusinessPayloads.Receipt.class : BusinessPayloads.Invoice.class,
          dto.getClass());
      contracts.business(type, contracts.empty(type));

      ObjectNode unknownKey = base.deepCopy();
      unknownKey.put(fixture.path("unknown_key").asText(), "x");
      assertInvalid(type, unknownKey, type + ".unknown_key");

      for (JsonNode field : fixture.path("required_fields").path(type)) {
        ObjectNode missing = base.deepCopy();
        missing.remove(field.asText());
        assertInvalid(type, missing, type + ".missing." + field.asText());
      }
      for (JsonNode field : fixture.path("required_item_fields")) {
        ObjectNode missing = base.deepCopy();
        ((ObjectNode) missing.path("items").get(0)).remove(field.asText());
        assertInvalid(type, missing, type + ".items.missing." + field.asText());
      }

      ObjectNode thirtyItems = base.deepCopy();
      ArrayNode acceptedItems = thirtyItems.putArray("items");
      for (int i = 0; i < fixture.path("max_items").asInt(); i++)
        acceptedItems.add(base.path("items").get(0).deepCopy());
      contracts.business(type, thirtyItems);

      ObjectNode thirtyOneItems = thirtyItems.deepCopy();
      thirtyOneItems.withArray("items").add(base.path("items").get(0).deepCopy());
      assertInvalid(type, thirtyOneItems, "31 items must be rejected");

      for (JsonNode field : fixture.path("wrong_type_fields").path(type)) {
        ObjectNode invalid = base.deepCopy();
        invalid.set(field.asText(), mapper.createObjectNode());
        assertInvalid(type, invalid, type + "." + field.asText());
      }

      for (JsonNode field : fixture.path("wrong_type_item_fields")) {
        ObjectNode invalid = base.deepCopy();
        ((ObjectNode) invalid.path("items").get(0)).put(field.asText(), 7);
        assertInvalid(type, invalid, type + ".items." + field.asText());
      }

      for (JsonNode wrongItem : fixture.path("wrong_type_items")) {
        ObjectNode invalid = base.deepCopy();
        invalid.withArray("items").set(0, wrongItem.deepCopy());
        assertInvalid(type, invalid, type + ".items[0]");
      }

      for (JsonNode path : fixture.path("decimal_json_number_fields").path(type)) {
        ObjectNode invalid = base.deepCopy();
        setPointer(invalid, path.asText(), mapper.getNodeFactory().numberNode(45000.5));
        assertInvalid(type, invalid, type + path.asText());
      }

      for (JsonNode path : fixture.path("integer_json_number_fields").path(type)) {
        ObjectNode invalid = base.deepCopy();
        setPointer(invalid, path.asText(), mapper.getNodeFactory().numberNode(45000));
        assertInvalid(type, invalid, type + path.asText());
      }

      JsonNode dateCase = fixture.path("invalid_calendar_dates").path(type);
      ObjectNode invalidDate = base.deepCopy();
      setPointer(invalidDate, dateCase.path("path").asText(), mapper.getNodeFactory().textNode(dateCase.path("value").asText()));
      assertTrue(
          contracts.issues(type, invalidDate).findValuesAsText("code").contains("INVALID_DATE"),
          type + " invalid calendar date");
    }
  }

  @Test
  void versionedExtractionAndExportEnvelopesRequireMatchingSchemaVersion() {
    for (String type : List.of("receipt", "invoice")) {
      for (JsonNode envelopeNode : fixture.path("versioned_envelopes")) {
        String envelopeType = envelopeNode.asText();
        ObjectNode valid = versionedEnvelope(type, envelopeType, "valid");
        validateEnvelope(type, envelopeType, valid);

        for (JsonNode schemaCaseNode : fixture.path("schema_version_cases")) {
          String schemaCase = schemaCaseNode.asText();
          ObjectNode invalid = versionedEnvelope(type, envelopeType, schemaCase);
          assertThrows(
              ApiException.class,
              () -> validateEnvelope(type, envelopeType, invalid),
              type + "." + envelopeType + ".schema_version." + schemaCase);
        }
      }
    }
  }

  private void validateEnvelope(String type, String envelopeType, JsonNode envelope) {
    if (envelopeType.equals("extraction"))
      contracts.extraction(
          type,
          "00000000-0000-4000-8000-000000000001",
          "00000000-0000-4000-8000-000000000002",
          "fixture.v1",
          envelope);
    else contracts.export(envelope);
  }

  private ObjectNode versionedEnvelope(String type, String envelopeType, String schemaCase) {
    ObjectNode envelope = mapper.createObjectNode();
    if (envelopeType.equals("extraction")) {
      envelope.put("run_id", "00000000-0000-4000-8000-000000000001");
      envelope.put("job_id", "00000000-0000-4000-8000-000000000002");
    } else {
      envelope.put("export_version", 1);
      envelope.put("document_id", "00000000-0000-4000-8000-000000000001");
      envelope.put("revision_id", "00000000-0000-4000-8000-000000000002");
    }
    envelope.put("document_type", type);
    if (schemaCase.equals("wrong"))
      envelope.put("schema_version", type.equals("receipt") ? "invoice.v1" : "receipt.v1");
    else if (schemaCase.equals("valid")) envelope.put("schema_version", type + ".v1");
    envelope.put("language", "vi");
    envelope.set("payload", fixture.path("payloads").path(type).deepCopy());
    if (envelopeType.equals("extraction")) {
      envelope.putArray("field_metadata");
      envelope.putArray("issues");
      ObjectNode provenance = envelope.putObject("provenance");
      provenance.put("pipeline_manifest_id", "fixture.v1");
      provenance.put("ocr_version", "fixture.v1");
      provenance.put("extractor_release_id", "fixture.v1");
      provenance.put("normalizer_version", "business.v1");
    }
    return envelope;
  }

  private void assertInvalid(String type, JsonNode payload, String context) {
    assertThrows(ApiException.class, () -> contracts.business(type, payload), context);
  }

  private void setPointer(ObjectNode root, String pointer, JsonNode value) {
    String[] parts = pointer.substring(1).split("/");
    JsonNode current = root;
    for (int i = 0; i < parts.length - 1; i++)
      current = current.isArray() ? current.path(Integer.parseInt(parts[i])) : current.path(parts[i]);
    String last = parts[parts.length - 1];
    if (current.isArray()) ((ArrayNode) current).set(Integer.parseInt(last), value);
    else ((ObjectNode) current).set(last, value);
  }

  private Path sharedFixturePath() {
    Path fromRoot = Path.of("tests/fixtures/contracts/business-validation.json");
    if (Files.exists(fromRoot)) return fromRoot;
    return Path.of("../tests/fixtures/contracts/business-validation.json");
  }
}
